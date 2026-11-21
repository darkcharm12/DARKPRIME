package com.darkprime.app

import android.app.KeyguardManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.StatFs
import android.provider.Settings
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import java.util.UUID

object DeviceInventory {

    private const val MAX_APPS = 1000
    private const val MAX_PERMISSIONS = 200

    fun deviceUuid(context: Context): String {
        val prefs = context.getSharedPreferences("darkprime_device", Context.MODE_PRIVATE)
        val existing = prefs.getString("uuid", null)
        if (!existing.isNullOrBlank()) return existing
        val value = UUID.randomUUID().toString()
        prefs.edit().putString("uuid", value).apply()
        return value
    }

    private fun nowIso(): String =
        java.time.Instant.now().toString().replace(Regex("\\.\\d+Z$"), "Z")

    fun collect(context: Context): JSONObject {
        val pm = context.packageManager
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        val keyguard = context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        val ownAdmin = ComponentName(context, DeviceAdminReceiver::class.java)
        val adminActive = dpm.isAdminActive(ownAdmin)

        val installed = pm.getInstalledPackages(PackageManager.GET_PERMISSIONS)
            .sortedBy { it.packageName }
            .take(MAX_APPS)
            .map { info ->
                val perms = (info.requestedPermissions ?: emptyArray())
                    .take(MAX_PERMISSIONS)
                    .map { it.toString() }
                val label = runCatching { info.applicationInfo?.loadLabel(pm)?.toString() }
                    .getOrNull() ?: info.packageName
                jsonObject(
                    "package" to info.packageName,
                    "label" to label,
                    "version_name" to (info.versionName ?: ""),
                    "version_code" to (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) info.longVersionCode else info.versionCode.toLong()),
                    "system" to ((info.applicationInfo?.flags ?: 0) and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0,
                    "requested_permissions" to perms
                )
            }

        val batteryIntent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = batteryIntent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryIntent?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val percent = if (level >= 0 && scale > 0) (level * 100) / scale else -1
        val plugged = batteryIntent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0
        val health = batteryIntent?.getIntExtra(BatteryManager.EXTRA_HEALTH, 0) ?: 0

        val stats = StatFs(context.getExternalFilesDir(null)?.path ?: context.filesDir.path)
        val total = stats.blockCountLong * stats.blockSizeLong
        val available = stats.availableBlocksLong * stats.blockSizeLong
        val freePercent = if (total > 0) ((available * 100) / total).toInt() else -1

        val accessibilityRaw = Settings.Secure.getString(
            context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ).orEmpty()
        val accessibility = if (accessibilityRaw.isBlank()) emptyList<String>()
        else accessibilityRaw.split(':').map { it.trim() }.filter { it.isNotBlank() }

        val admins = if (adminActive) listOf("$ownAdmin") else emptyList<String>()

        val connectivity = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivity.activeNetwork
        val capabilities = network?.let { connectivity.getNetworkCapabilities(it) }
        val networkType = when {
            capabilities == null -> "none"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "mobile"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "other"
        }

        return jsonObject(
            "captured_at" to nowIso(),
            "client_version" to "1.0.0",
            "device" to jsonObject(
                "model" to Build.MODEL,
                "brand" to Build.BRAND,
                "manufacturer" to Build.MANUFACTURER,
                "android_version" to Build.VERSION.RELEASE,
                "sdk" to Build.VERSION.SDK_INT,
                "security_patch" to (Build.VERSION.SECURITY_PATCH ?: ""),
                "locale" to Locale.getDefault().toString()
            ),
            "battery" to jsonObject(
                "level" to percent,
                "charging" to (plugged != 0),
                "health" to health
            ),
            "storage" to jsonObject(
                "total_bytes" to total,
                "free_bytes" to available,
                "free_percent" to freePercent
            ),
            "apps" to JSONArray(installed),
            "security" to jsonObject(
                "accessibility_services" to accessibility,
                "device_admins" to admins,
                "darkprime_admin_active" to adminActive,
                "device_owner" to dpm.isDeviceOwnerApp(context.packageName),
                "screen_lock_secure" to keyguard.isDeviceSecure(),
                "usb_debugging" to (Settings.Secure.getInt(context.contentResolver, "adb_enabled", 0) == 1),
                "developer_options" to (Settings.Global.getInt(context.contentResolver, "development_settings_enabled", 0) == 1),
                "unknown_sources" to (Settings.Secure.getInt(context.contentResolver, "install_non_market_apps", 0) == 1),
                "encryption_status" to dpm.storageEncryptionStatus
            ),
            "network" to jsonObject("type" to networkType),
            "scope" to jsonObject(
                "collected" to listOf("device_info", "battery", "storage", "apps", "permissions",
                    "accessibility_services", "device_admin_status", "network_type"),
                "excluded" to listOf("camera", "microphone", "messages", "contacts", "call_logs",
                    "credentials", "browsing_history", "files", "location")
            )
        )
    }
}
