package com.darkprime.app

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import androidx.work.WorkManager

object EnrollmentController {

    fun unenroll(context: Context, onDone: (Boolean, String) -> Unit) {
        val manager = EnrollmentManager(context)
        val server = manager.serverUrl
        val token = manager.deviceToken

        Thread {
            var success = true
            var message = "Local monitoring stopped and enrollment removed."
            if (!server.isNullOrBlank() && !token.isNullOrBlank()) {
                try {
                    val api = ApiClient(server, token)
                    api.requestUnenroll()
                    api.confirmUnenroll()
                } catch (e: Exception) {
                    success = false
                    message = "Local monitoring stopped. Server revocation could not be confirmed: ${e.message}"
                }
            }
            manager.clear()
            WorkManager.getInstance(context).cancelUniqueWork(TelemetryWorker.WORK_NAME)
            context.stopService(Intent(context, MonitoringService::class.java))
            Handler(Looper.getMainLooper()).post { onDone(success, message) }
        }.start()
    }
}
