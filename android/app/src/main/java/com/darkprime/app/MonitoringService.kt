package com.darkprime.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.util.Log
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import java.io.ByteArrayOutputStream

class MonitoringService : Service() {

    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var captureThread: HandlerThread? = null
    private var captureHandler: Handler? = null
    private var activeSessionId: Int? = null
    private var screenCapturing = false
    private var lastFrameAtMs = 0L

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopScreenCapture(finishOnServer = false)
                EnrollmentController.unenroll(this) { success, message ->
                    Toast.makeText(this, message, Toast.LENGTH_LONG).show()
                    if (success) stopSelf()
                }
                return START_NOT_STICKY
            }
            ACTION_STOP_SCREEN -> {
                stopScreenCapture(finishOnServer = true)
                return START_STICKY
            }
            ACTION_START_SCREEN -> {
                if (!EnrollmentManager(this).isEnrolled) {
                    stopSelf()
                    return START_NOT_STICKY
                }
                val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
                val resultData: Intent? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
                }
                val sessionId = intent.getIntExtra(EXTRA_SESSION_ID, -1)
                startForegroundForScreen(true)
                TelemetryWorker.schedule(this)
                if (resultCode == android.app.Activity.RESULT_OK && resultData != null && sessionId > 0) {
                    startScreenCapture(resultCode, resultData, sessionId)
                } else {
                    Toast.makeText(this, "Screen sharing was not approved.", Toast.LENGTH_LONG).show()
                    stopScreenCapture(finishOnServer = true)
                }
                return START_STICKY
            }
        }

        if (!EnrollmentManager(this).isEnrolled) {
            stopSelf()
            return START_NOT_STICKY
        }

        startForegroundForScreen(false)
        TelemetryWorker.schedule(this)
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopScreenCapture(finishOnServer = false)
        super.onDestroy()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "DARKPRIME monitoring status",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Visible notice that consent-based auditing or owner-approved screen sharing is active."
                setShowBadge(false)
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun startForegroundForScreen(screenActive: Boolean) {
        val notification = buildNotification(screenActive)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val type = if (screenActive) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            } else {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            }
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(screenActive: Boolean): Notification {
        val openIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val stopAction = if (screenActive) ACTION_STOP_SCREEN else ACTION_STOP
        val stopIntent = PendingIntent.getService(
            this, 1, Intent(this, MonitoringService::class.java).setAction(stopAction),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(
                if (screenActive) "DARKPRIME screen sharing active" else "DARKPRIME monitoring active"
            )
            .setContentText(
                if (screenActive) {
                    "Capture indicator is visible. Tap Stop to end screen sharing now."
                } else {
                    "Auditing is visible. Tap to review or stop at any time."
                }
            )
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(R.drawable.ic_stat, "Review", openIntent)
            .addAction(R.drawable.ic_stat, if (screenActive) "Stop screen" else "Stop", stopIntent)
            .build()
    }

    private fun apiClient(): ApiClient? {
        val manager = EnrollmentManager(this)
        val server = manager.serverUrl ?: return null
        val token = manager.deviceToken ?: return null
        return ApiClient(server, token)
    }

    private fun startScreenCapture(resultCode: Int, resultData: Intent, sessionId: Int) {
        if (screenCapturing) stopScreenCapture(finishOnServer = false)
        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjection = try {
            manager.getMediaProjection(resultCode, resultData)
        } catch (e: Exception) {
            Log.w(TAG, "MediaProjection could not start", e)
            Toast.makeText(this, "Screen sharing could not start.", Toast.LENGTH_LONG).show()
            return
        }
        activeSessionId = sessionId
        screenCapturing = true
        lastFrameAtMs = 0L

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            mediaProjection?.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    stopScreenCapture(finishOnServer = true)
                }
            }, Handler(Looper.getMainLooper()))
        }

        val metrics = resources.displayMetrics
        val width = 480.coerceAtMost(metrics.widthPixels)
        val height = (width * metrics.heightPixels / metrics.widthPixels).coerceAtMost(metrics.heightPixels)
        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        imageReader = reader
        captureThread = HandlerThread("darkprime-capture").apply { start() }
        captureHandler = Handler(captureThread!!.looper)
        reader.setOnImageAvailableListener({ source -> captureFrame(source) }, captureHandler)
        virtualDisplay = mediaProjection?.createVirtualDisplay(
            "DARKPRIME",
            width,
            height,
            metrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.surface,
            null,
            captureHandler
        )
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification(true))
    }

    private fun captureFrame(reader: ImageReader) {
        val sessionId = activeSessionId ?: return
        if (!screenCapturing || System.currentTimeMillis() - lastFrameAtMs < 1500L) return
        val image = reader.acquireLatestImage() ?: return
        try {
            val bytes = encodeFrame(image) ?: return
            lastFrameAtMs = System.currentTimeMillis()
            val api = apiClient() ?: return
            val heartbeat = api.screenHeartbeat(sessionId)
            if (heartbeat.optString("status") != "active" || heartbeat.optBoolean("stop_requested")) {
                stopScreenCapture(finishOnServer = true)
                return
            }
            api.postScreenFrame(sessionId, bytes)
        } catch (e: ApiException) {
            when (e.status) {
                401, 403, 410 -> {
                    EnrollmentManager(this).clear()
                    stopSelf()
                }
                409 -> stopScreenCapture(finishOnServer = true)
                else -> Log.w(TAG, "Screen frame upload failed (${e.status})")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Screen frame capture failed", e)
        } finally {
            image.close()
        }
    }

    private fun encodeFrame(image: Image): ByteArray? {
        val plane = image.planes.firstOrNull() ?: return null
        val pixelStride = plane.pixelStride
        val rowStride = plane.rowStride
        val rowPadding = rowStride - pixelStride * image.width
        val bitmapWidth = image.width + rowPadding / pixelStride
        val full = Bitmap.createBitmap(bitmapWidth, image.height, Bitmap.Config.ARGB_8888)
        full.copyPixelsFromBuffer(plane.buffer)
        val cropped = Bitmap.createBitmap(full, 0, 0, image.width, image.height)
        val scaledHeight = (480f * image.height / image.width).toInt().coerceAtLeast(1)
        val scaled = Bitmap.createScaledBitmap(cropped, 480, scaledHeight, true)
        val output = ByteArrayOutputStream()
        scaled.compress(Bitmap.CompressFormat.JPEG, 55, output)
        full.recycle()
        cropped.recycle()
        scaled.recycle()
        return output.toByteArray()
    }

    private fun stopScreenCapture(finishOnServer: Boolean) {
        val sessionId = activeSessionId
        if (!screenCapturing && sessionId == null) return
        screenCapturing = false
        activeSessionId = null
        imageReader?.setOnImageAvailableListener(null, null)
        virtualDisplay?.release()
        mediaProjection?.stop()
        imageReader?.close()
        captureThread?.quitSafely()
        virtualDisplay = null
        mediaProjection = null
        imageReader = null
        captureHandler = null
        captureThread = null
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification(false))
        if (finishOnServer && sessionId != null) {
            Thread {
                try {
                    apiClient()?.stopScreenSession(sessionId)
                } catch (_: Exception) {
                    Log.w(TAG, "Could not confirm screen session stop")
                }
            }.start()
        }
    }

    companion object {
        private const val TAG = "DARKPRIME-Screen"
        private const val CHANNEL_ID = "darkprime_status"
        private const val NOTIFICATION_ID = 4101
        const val ACTION_STOP = "com.darkprime.app.STOP_MONITORING"
        const val ACTION_START_SCREEN = "com.darkprime.app.START_SCREEN"
        const val ACTION_STOP_SCREEN = "com.darkprime.app.STOP_SCREEN"
        const val EXTRA_RESULT_CODE = "com.darkprime.app.RESULT_CODE"
        const val EXTRA_RESULT_DATA = "com.darkprime.app.RESULT_DATA"
        const val EXTRA_SESSION_ID = "com.darkprime.app.SESSION_ID"

        fun start(context: Context) {
            val intent = Intent(context, MonitoringService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun startScreen(context: Context, resultCode: Int, resultData: Intent, sessionId: Int) {
            val intent = Intent(context, MonitoringService::class.java)
                .setAction(ACTION_START_SCREEN)
                .putExtra(EXTRA_RESULT_CODE, resultCode)
                .putExtra(EXTRA_RESULT_DATA, resultData)
                .putExtra(EXTRA_SESSION_ID, sessionId)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stopScreen(context: Context) {
            val intent = Intent(context, MonitoringService::class.java).setAction(ACTION_STOP_SCREEN)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
