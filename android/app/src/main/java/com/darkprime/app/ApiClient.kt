package com.darkprime.app

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.net.URL
import java.util.concurrent.TimeUnit

class ApiException(val status: Int, message: String) : Exception(message)

internal fun jsonObject(vararg pairs: Pair<String, Any?>): JSONObject {
    val obj = JSONObject()
    for ((key, value) in pairs) {
        when (value) {
            null -> obj.put(key, JSONObject.NULL)
            is JSONObject, is JSONArray, is String, is Number, is Boolean -> obj.put(key, value)
            is List<*> -> obj.put(key, JSONArray(value))
            else -> obj.put(key, value.toString())
        }
    }
    return obj
}

class ApiClient(private val serverUrl: String, private val deviceToken: String? = null) {

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .followRedirects(false)
        .build()

    private val base: String = serverUrl.trim().trimEnd('/')

    init {
        require(isHttps(base)) { "The server URL must use HTTPS." }
    }

    private fun isHttps(value: String): Boolean = runCatching {
        val url = URL(value)
        url.protocol.equals("https", ignoreCase = true)
    }.getOrDefault(false)

    private fun call(path: String, body: JSONObject, token: String? = deviceToken): JSONObject {
        val builder = Request.Builder().url(base + path)
        if (!token.isNullOrBlank()) builder.header("Authorization", "Bearer $token")
        val request = builder
            .header("Accept", "application/json")
            .post(body.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        client.newCall(request).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw ApiException(response.code, text.ifBlank { response.message })
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        }
    }

    fun enroll(
        enrollmentToken: String,
        uuid: String,
        name: String,
        model: String,
        androidVersion: String,
        consentAt: String
    ): JSONObject = call(
        "/api/devices/enroll",
        jsonObject(
            "enrollment_token" to enrollmentToken,
            "device_uuid" to uuid,
            "name" to name,
            "model" to model,
            "android_version" to androidVersion,
            "client_version" to "1.0.0",
            "consent" to jsonObject("accepted" to true, "at" to consentAt)
        ),
        token = null
    )

    fun telemetry(payload: JSONObject): JSONObject = call("/api/devices/me/telemetry", payload)

    fun myDevice(): JSONObject {
        val builder = Request.Builder().url(base + "/api/devices/me")
        if (!deviceToken.isNullOrBlank()) builder.header("Authorization", "Bearer $deviceToken")
        val request = builder.header("Accept", "application/json").get().build()
        client.newCall(request).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw ApiException(response.code, text.ifBlank { response.message })
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        }
    }

    fun requestUnenroll(): JSONObject = call("/api/devices/me/unenroll/request", jsonObject())

    fun confirmUnenroll(): JSONObject = call("/api/devices/me/unenroll/confirm", jsonObject())
}
