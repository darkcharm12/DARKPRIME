package com.darkprime.app

import android.Manifest
import android.app.AlertDialog
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import java.time.Instant

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var detailText: TextView
    private lateinit var enrollPanel: View
    private lateinit var serverUrlInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var consentCheck: CheckBox
    private lateinit var enrollButton: Button
    private lateinit var unenrollButton: Button
    private lateinit var adminButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        detailText = findViewById(R.id.detailText)
        enrollPanel = findViewById(R.id.enrollPanel)
        serverUrlInput = findViewById(R.id.serverUrlInput)
        tokenInput = findViewById(R.id.tokenInput)
        consentCheck = findViewById(R.id.consentCheck)
        enrollButton = findViewById(R.id.enrollButton)
        unenrollButton = findViewById(R.id.unenrollButton)
        adminButton = findViewById(R.id.adminButton)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 101)
        }

        enrollButton.setOnClickListener { attemptEnroll() }
        unenrollButton.setOnClickListener { confirmUnenroll() }
        adminButton.setOnClickListener { showAdminStatus() }
        refresh()
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun refresh() {
        val manager = EnrollmentManager(this)
        if (manager.isEnrolled) {
            enrollPanel.visibility = View.GONE
            unenrollButton.visibility = View.VISIBLE
            statusText.text = "MONITORING ACTIVE"
            detailText.text = listOf(
                "Device ID: ${manager.deviceId}",
                "Server: ${manager.serverUrl}",
                "Consent recorded: ${manager.consentAt}",
                "A persistent notification is shown while monitoring is active.",
                "No camera, microphone, message, contact, credential, or file access is used."
            ).joinToString("\n")
            MonitoringService.start(this)
        } else {
            enrollPanel.visibility = View.VISIBLE
            unenrollButton.visibility = View.GONE
            statusText.text = "NOT ENROLLED"
            detailText.text = "Enrollment requires a one-time token from the operator dashboard and your explicit consent."
            stopService(Intent(this, MonitoringService::class.java))
        }
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
                val message = if (e is ApiException) "Enrollment failed (HTTP ${e.status})." else "Enrollment failed: ${e.message}"
                runOnUiThread {
                    enrollButton.isEnabled = true
                    statusText.text = message
                }
            }
        }.start()
    }

    private fun confirmUnenroll() {
        AlertDialog.Builder(this)
            .setTitle("Stop monitoring and unenroll?")
            .setMessage("This clears the local enrollment token, stops the foreground service, cancels scheduled reports, and revokes the server-side token.")
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
}
