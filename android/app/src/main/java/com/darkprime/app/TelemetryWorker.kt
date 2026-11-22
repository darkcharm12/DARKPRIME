package com.darkprime.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
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
            val screenRequested = (0 until (pending?.length() ?: 0)).any {
                pending?.optString(it) == "screen_session"
            }
            if (screenRequested) showScreenRequestNotification()
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

    private fun showScreenRequestNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                REQUEST_CHANNEL_ID,
                "DARKPRIME approval requests",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Prompts the owner to review a screen-sharing request."
            }
            applicationContext.getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }
        val open = PendingIntent.getActivity(
            applicationContext,
            2,
            Intent(applicationContext, MainActivity::class.java).putExtra(EXTRA_OPEN_SCREEN_REQUEST, true),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(applicationContext, REQUEST_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle("DARKPRIME screen-sharing request")
            .setContentText("Open DARKPRIME to approve or decline. Nothing is shared until you approve.")
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(applicationContext).notify(REQUEST_NOTIFICATION_ID, notification)
    }

    companion object {
        const val WORK_NAME = "darkprime-telemetry"
        const val EXTRA_OPEN_SCREEN_REQUEST = "com.darkprime.app.OPEN_SCREEN_REQUEST"
        private const val REQUEST_CHANNEL_ID = "darkprime_requests"
        private const val REQUEST_NOTIFICATION_ID = 4202

        fun cancelScreenRequestNotification(context: Context) {
            NotificationManagerCompat.from(context).cancel(REQUEST_NOTIFICATION_ID)
        }

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
