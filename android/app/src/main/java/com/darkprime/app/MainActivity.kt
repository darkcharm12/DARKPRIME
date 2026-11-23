package com.darkprime.app

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.time.Instant

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var detailText: TextView
    private lateinit var screenStatusText: TextView
    private lateinit var enrollPanel: View
    private lateinit var serverUrlInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var consentCheck: CheckBox
    private lateinit var enrollButton: Button
    private lateinit var unenrollButton: Button
    private lateinit var stopScreenButton: Button
    private lateinit var adminButton: Button
    private lateinit var updateUrlButton: Button

    private val mainHandler = Handler(Looper.getMainLooper())
    private var pendingSessionId: Int? = null
    private var promptShownSessionId: Int? = null
    private var projectionSessionId: Int? = null
    private var currentScreenSessionId: Int? = null
    private var screenCheckInFlight = false

    private val screenPoll = object : Runnable {
        override fun run() {
            checkScreenSessions()
            mainHandler.postDelayed(this, 5000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        detailText = findViewById(R.id.detailText)
        screenStatusText = findViewById(R.id.screenStatusText)
        enrollPanel = findViewById(R.id.enrollPanel)
        serverUrlInput = findViewById(R.id.serverUrlInput)
        tokenInput = findViewById(R.id.tokenInput)
        consentCheck = findViewById(R.id.consentCheck)
        enrollButton = findViewById(R.id.enrollButton)
        unenrollButton = findViewById(R.id.unenrollButton)
        stopScreenButton = findViewById(R.id.stopScreenButton)
        adminButton = findViewById(R.id.adminButton)
        updateUrlButton = findViewById(R.id.updateUrlButton)

        enrollButton.setOnClickListener { attemptEnroll() }
        unenrollButton.setOnClickListener { confirmUnenroll() }
        stopScreenButton.setOnClickListener { stopCurrentScreenSession() }
        adminButton.setOnClickListener { showAdminStatus() }
        updateUrlButton.setOnClickListener { promptUpdateServerUrl() }
        refresh()
    }

    override fun onResume() {
        super.onResume()
        refresh()
        mainHandler.removeCallbacks(screenPoll)
        mainHandler.post(screenPoll)
    }

    override fun onPause() {
        mainHandler.removeCallbacks(screenPoll)
        super.onPause()
    }

    private fun refresh() {
        val manager = EnrollmentManager(this)
        if (manager.isEnrolled) {
            enrollPanel.visibility = View.GONE
            unenrollButton.visibility = View.VISIBLE
            updateUrlButton.visibility = View.VISIBLE
            statusText.text = "MONITORING ACTIVE"
            detailText.text = listOf(
                "Device ID: ${manager.deviceId}",
                "Server: ${manager.serverUrl}",
                "Consent recorded: ${manager.consentAt}",
                "A persistent notification is shown while monitoring is active.",
                "Screen frames are sent only after a separate approval and Android capture consent."
            ).joinToString("\n")
            MonitoringService.start(this)
            checkScreenSessions()
        } else {
            enrollPanel.visibility = View.VISIBLE
            unenrollButton.visibility = View.GONE
            stopScreenButton.visibility = View.GONE
            updateUrlButton.visibility = View.GONE
            screenStatusText.text = "Screen sharing: off (not enrolled)"
            statusText.text = "NOT ENROLLED"
            detailText.text = "Enrollment requires a one-time token from the operator dashboard and your explicit consent. For remote/cross-network use, enter the public HTTPS tunnel URL."
            stopService(Intent(this, MonitoringService::class.java))
        }
    }

    private fun apiClient(): ApiClient? {
        val manager = EnrollmentManager(this)
        val server = manager.serverUrl ?: return null
        val token = manager.deviceToken ?: return null
        return ApiClient(server, token)
    }

    private fun checkScreenSessions() {
        if (screenCheckInFlight) return
        val api = apiClient()
        if (api == null) {
            screenStatusText.text = "Screen sharing: off (not enrolled)"
            stopScreenButton.visibility = View.GONE
            return
        }
        screenCheckInFlight = true
        Thread {
            try {
                val body = api.screenSessions()
                val pending = body.optJSONObject("pending")
                val active = body.optJSONObject("active")
                runOnUiThread {
                    if (active != null) {
                        currentScreenSessionId = active.optInt("id")
                        screenStatusText.text = "Screen sharing: ACTIVE — visible on screen"
                        stopScreenButton.visibility = View.VISIBLE
                    } else {
                        currentScreenSessionId = null
                        stopScreenButton.visibility = View.GONE
                        screenStatusText.text = if (pending != null) {
                            "Screen sharing: approval requested"
                        } else {
                            "Screen sharing: off"
                        }
                    }
                    if (pending != null) {
                        val id = pending.optInt("id")
                        if (promptShownSessionId != id && projectionSessionId == null) {
                            showScreenRequestDialog(id)
                        }
                    } else {
                        promptShownSessionId = null
                        TelemetryWorker.cancelScreenRequestNotification(this)
                    }
                }
            } catch (e: ApiException) {
                runOnUiThread {
                    screenStatusText.text = "Screen sharing: status unavailable (HTTP ${e.status}). If remote URL changed, use Update server URL."
                }
            } catch (e: Exception) {
                val detail = when (e) {
                    is java.net.UnknownHostException -> "server not found"
                    is java.net.ConnectException, is java.net.SocketTimeoutException -> "cannot reach server/tunnel"
                    is javax.net.ssl.SSLException -> "TLS/certificate error"
                    else -> "connection error"
                }
                runOnUiThread { screenStatusText.text = "Screen sharing: $detail. Check public URL/tunnel." }
            } finally {
                screenCheckInFlight = false
            }
        }.start()
    }

    private fun showScreenRequestDialog(sessionId: Int) {
        promptShownSessionId = sessionId
        AlertDialog.Builder(this)
            .setCancelable(false)
            .setTitle(R.string.screen_request_title)
            .setMessage(R.string.screen_request_message)
            .setNegativeButton("Decline") { _, _ -> declineScreenSession(sessionId) }
            .setPositiveButton("Approve and continue") { _, _ -> beginScreenApproval(sessionId) }
            .show()
    }

    private fun beginScreenApproval(sessionId: Int) {
        pendingSessionId = sessionId
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            Toast.makeText(this, R.string.screen_notification_rationale, Toast.LENGTH_LONG).show()
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
            return
        }
        launchProjectionConsent(sessionId)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_NOTIFICATIONS) return
        val sessionId = pendingSessionId ?: return
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            launchProjectionConsent(sessionId)
        } else {
            pendingSessionId = null
            declineScreenSession(sessionId)
            Toast.makeText(this, "Screen sharing needs the visible notification permission.", Toast.LENGTH_LONG).show()
        }
    }

    private fun launchProjectionConsent(sessionId: Int) {
        projectionSessionId = sessionId
        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        startActivityForResult(manager.createScreenCaptureIntent(), REQUEST_MEDIA_PROJECTION)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_MEDIA_PROJECTION) return
        val sessionId = projectionSessionId ?: return
        projectionSessionId = null
        pendingSessionId = null
        if (resultCode != Activity.RESULT_OK || data == null) {
            declineScreenSession(sessionId)
            return
        }
        screenStatusText.text = "Screen sharing: starting..."
        Thread {
            try {
                val api = apiClient() ?: throw IllegalStateException("Enrollment changed")
                api.approveScreenSession(sessionId, Instant.now().toString())
                MonitoringService.startScreen(this, resultCode, data, sessionId)
                runOnUiThread {
                    currentScreenSessionId = sessionId
                    screenStatusText.text = "Screen sharing: ACTIVE — visible on screen"
                    stopScreenButton.visibility = View.VISIBLE
                    Toast.makeText(this, "Screen sharing started. Stop any time from here or the notification.", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                runCatching { apiClient()?.declineScreenSession(sessionId) }
                runOnUiThread {
                    screenStatusText.text = "Screen sharing: could not start"
                    stopScreenButton.visibility = View.GONE
                    Toast.makeText(this, "Screen sharing was not approved by the server.", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun declineScreenSession(sessionId: Int) {
        screenStatusText.text = "Screen sharing: declined"
        stopScreenButton.visibility = View.GONE
        Thread {
            runCatching { apiClient()?.declineScreenSession(sessionId) }
        }.start()
    }

    private fun stopCurrentScreenSession() {
        val sessionId = currentScreenSessionId ?: return
        stopScreenButton.isEnabled = false
        MonitoringService.stopScreen(this)
        Thread {
            try {
                apiClient()?.stopScreenSession(sessionId)
            } catch (_: Exception) {
                runCatching { apiClient()?.stopScreenSession(sessionId) }
            }
            runOnUiThread {
                stopScreenButton.isEnabled = true
                stopScreenButton.visibility = View.GONE
                screenStatusText.text = "Screen sharing: off"
                currentScreenSessionId = null
            }
        }.start()
    }

    private fun attemptEnroll() {
        val url = serverUrlInput.text.toString().trim().trimEnd('/')
        val token = tokenInput.text.toString().trim()
        if (!url.startsWith("https://", ignoreCase = true)) {
            statusText.text = "Server URL must start with https://"
            return
        }
        if (token.isBlank()) {
            statusText.text = "Enter the one-time enrollment token."
            return
        }
        if (!consentCheck.isChecked) {
            statusText.text = "Explicit consent is required before enrollment."
            return
        }

        enrollButton.isEnabled = false
        statusText.text = "Enrolling with $url ..."
        val consentAt = Instant.now().toString()

        Thread {
            try {
                val api = ApiClient(url)
                val response = api.enroll(
                    enrollmentToken = token,
                    uuid = DeviceInventory.deviceUuid(applicationContext),
                    name = Build.MODEL,
                    model = Build.MODEL,
                    androidVersion = Build.VERSION.RELEASE,
                    consentAt = consentAt
                )
                EnrollmentManager(applicationContext).save(
                    url, response.getString("token"), response.getInt("device_id"), consentAt
                )
                runOnUiThread {
                    tokenInput.text?.clear()
                    enrollButton.isEnabled = true
                    refresh()
                    Toast.makeText(this, "Enrolled. Visible monitoring is now active.", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                val detail = when (e) {
                    is ApiException -> "HTTP ${e.status}"
                    is java.net.UnknownHostException -> "server address not found. Use a public HTTPS URL/tunnel for remote access."
                    is java.net.ConnectException, is java.net.SocketTimeoutException -> "cannot reach server. Check URL, internet, and that server/tunnel is running."
                    is javax.net.ssl.SSLException -> "TLS/certificate error. Use a trusted HTTPS certificate or install the matching APK for your lab cert."
                    else -> e.message ?: "unknown error"
                }
                runOnUiThread {
                    enrollButton.isEnabled = true
                    statusText.text = "Enrollment failed: $detail"
                }
            }
        }.start()
    }

    private fun promptUpdateServerUrl() {
        val manager = EnrollmentManager(this)
        val input = EditText(this).apply {
            setText(manager.serverUrl ?: "")
            hint = "https://your-public-url.trycloudflare.com"
        }
        AlertDialog.Builder(this)
            .setTitle("Update server URL")
            .setMessage("Use this when your public tunnel/domain changes. The device must already be enrolled; this keeps the same device token.")
            .setView(input)
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Save") { _, _ ->
                val url = input.text.toString().trim().trimEnd('/')
                if (!url.startsWith("https://", ignoreCase = true)) {
                    Toast.makeText(this, "URL must start with https://", Toast.LENGTH_LONG).show()
                    return@setPositiveButton
                }
                Thread {
                    try {
                        val api = ApiClient(url, manager.deviceToken ?: "")
                        api.heartbeat(Instant.now().toString())
                        EnrollmentManager(applicationContext).save(url, manager.deviceToken ?: "", manager.deviceId, manager.consentAt ?: "")
                        runOnUiThread {
                            Toast.makeText(this, "Server URL updated.", Toast.LENGTH_LONG).show()
                            refresh()
                        }
                    } catch (e: Exception) {
                        val detail = when (e) {
                            is ApiException -> "HTTP ${e.status}"
                            is java.net.UnknownHostException -> "address not found"
                            is java.net.ConnectException, is java.net.SocketTimeoutException -> "cannot reach server/tunnel"
                            is javax.net.ssl.SSLException -> "TLS/certificate error"
                            else -> e.message ?: "unknown error"
                        }
                        runOnUiThread { Toast.makeText(this, "Update failed: $detail", Toast.LENGTH_LONG).show() }
                    }
                }.start()
            }
            .show()
    }

    private fun confirmUnenroll() {
        AlertDialog.Builder(this)
            .setTitle("Stop monitoring and unenroll?")
            .setMessage("This also ends any active screen session, clears the local enrollment token, stops the foreground service, cancels scheduled reports, and revokes the server-side token.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Stop and unenroll") { _, _ ->
                unenrollButton.isEnabled = false
                statusText.text = "Removing enrollment ..."
                EnrollmentController.unenroll(this) { _, message ->
                    unenrollButton.isEnabled = true
                    statusText.text = message
                    refresh()
                }
            }
            .show()
    }

    private fun showAdminStatus() {
        val dpm = getSystemService(DEVICE_POLICY_SERVICE) as DevicePolicyManager
        val own = ComponentName(this, DeviceAdminReceiver::class.java)
        val active = dpm.isAdminActive(own)
        AlertDialog.Builder(this)
            .setTitle("Device-admin status")
            .setMessage(if (active) "DARKPRIME's own device-admin receiver is active. No device-admin policies are used." else "DARKPRIME is not a device admin. Activating it is optional and reports only its own status.")
            .setNegativeButton("Close", null)
            .setPositiveButton(if (active) "Deactivate" else "Activate (optional)") { _, _ ->
                if (active) {
                    dpm.removeActiveAdmin(own)
                    showAdminStatus()
                } else {
                    val intent = Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN)
                        .putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, own)
                        .putExtra(DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                            "Optional: lets DARKPRIME report its own device-admin status. No policies are enforced.")
                    startActivity(intent)
                }
            }
            .show()
    }

    companion object {
        private const val REQUEST_NOTIFICATIONS = 102
        private const val REQUEST_MEDIA_PROJECTION = 103
    }
}
