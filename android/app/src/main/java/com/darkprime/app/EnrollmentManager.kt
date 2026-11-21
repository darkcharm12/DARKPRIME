package com.darkprime.app

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class EnrollmentManager(context: Context) {

    private val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()

    private val prefs = EncryptedSharedPreferences.create(
        context,
        "darkprime_secure_prefs",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    val isEnrolled: Boolean
        get() = !prefs.getString(KEY_TOKEN, null).isNullOrBlank() &&
                !prefs.getString(KEY_SERVER, null).isNullOrBlank()

    val serverUrl: String? get() = prefs.getString(KEY_SERVER, null)
    val deviceToken: String? get() = prefs.getString(KEY_TOKEN, null)
    val deviceId: Int get() = prefs.getInt(KEY_DEVICE_ID, -1)
    val consentAt: String? get() = prefs.getString(KEY_CONSENT, null)

    fun save(serverUrl: String, token: String, deviceId: Int, consentAt: String) {
        prefs.edit()
            .putString(KEY_SERVER, serverUrl.trim().trimEnd('/'))
            .putString(KEY_TOKEN, token)
            .putInt(KEY_DEVICE_ID, deviceId)
            .putString(KEY_CONSENT, consentAt)
            .apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val KEY_SERVER = "server_url"
        private const val KEY_TOKEN = "device_token"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_CONSENT = "consent_at"
    }
}
