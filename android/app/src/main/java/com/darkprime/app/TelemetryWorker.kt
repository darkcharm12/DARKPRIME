package com.darkprime.app

import android.content.Context
import android.content.Intent
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

class TelemetryWorker(appContext: Context, params: WorkerParameters) : Worker(appContext, params) {

    override fun doWork(): Result {
        val manager = EnrollmentManager(applicationContext)
        if (!manager.isEnrolled) return Result.success()

        val server = manager.serverUrl ?: return Result.success()
        val token = manager.deviceToken ?: return Result.success()

        return try {
            val api = ApiClient(server, token)
            val response = api.telemetry(DeviceInventory.collect(applicationContext))
            val pending = response.optJSONArray("pending_actions")
            val shouldUnenroll = (0 until (pending?.length() ?: 0)).any {
                pending?.optString(it) == "unenroll"
            }
            if (shouldUnenroll) {
                runCatching { api.requestUnenroll() }
                runCatching { api.confirmUnenroll() }
                manager.clear()
                WorkManager.getInstance(applicationContext).cancelUniqueWork(WORK_NAME)
                applicationContext.stopService(Intent(applicationContext, MonitoringService::class.java))
            }
            Result.success()
        } catch (e: ApiException) {
            if (e.status == 401 || e.status == 403 || e.status == 410) {
                manager.clear()
                WorkManager.getInstance(applicationContext).cancelUniqueWork(WORK_NAME)
                applicationContext.stopService(Intent(applicationContext, MonitoringService::class.java))
                Result.success()
            } else {
                Result.retry()
            }
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        const val WORK_NAME = "darkprime-telemetry"

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val periodic = PeriodicWorkRequestBuilder<TelemetryWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, periodic
            )
            val immediate = OneTimeWorkRequestBuilder<TelemetryWorker>()
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                "$WORK_NAME-now", ExistingWorkPolicy.REPLACE, immediate
            )
        }
    }
}
