package com.cortoba.warehouse

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

/**
 * A refusal the server sent, with the sentence it sent with it.
 *
 * The server writes its refusals in Arabic for this app ("هذا الرقم غير مسجَّل
 * في النظام…"), so the message is shown as-is rather than replaced by a generic
 * "something went wrong" the operator cannot act on.
 */
class ApiException(val status: Int, override val message: String, val code: String = "") :
    Exception(message)

data class Profile(
    val username: String,
    val displayName: String,
    val role: String,
    val phone: String,
    val pendingPhone: String?,
)

/**
 * The app's whole conversation with the server.
 *
 * `HttpURLConnection` rather than a networking library: the payloads are five
 * small JSON objects, and one fewer dependency is one fewer thing that can
 * break the build on a phone that must keep receiving updates.
 */
class Api(private val baseUrl: String) {

    private val root: String = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"

    fun version(installedCode: Int): UpdateInfo? =
        parseVersionResponse(
            request("api/mobile/version/?code=$installedCode", "GET").second
        )

    fun versionAnonymous(): UpdateInfo? =
        parseVersionResponse(request("api/mobile/version/", "GET").second)

    fun login(phone: String, password: String, device: String): Pair<String, Profile> {
        val body = JSONObject()
            .put("phone", phone)
            .put("password", password)
            .put("device", device)
            .toString()
        val (_, text) = request("api/mobile/login/", "POST", body)
        val json = JSONObject(text)
        val token = json.optString("token")
        if (token.isEmpty()) throw ApiException(500, "لم يُرجع الخادم جلسة.")
        return token to parseProfile(json.getJSONObject("user"))
    }

    fun me(token: String): Profile =
        parseProfile(JSONObject(request("api/mobile/me/", "GET", null, token).second))

    fun logout(token: String) {
        request("api/mobile/logout/", "POST", "{}", token)
    }

    /**
     * Ask for a new number. The app can only ASK: the server refuses any
     * attempt to write the phone directly, and nothing changes until a manager
     * approves the request in the web interface.
     */
    fun requestPhoneChange(token: String, newPhone: String, reason: String): String {
        val body = JSONObject()
            .put("requestedPhone", newPhone)
            .put("reason", reason)
            .toString()
        val (_, text) = request("api/mobile/phone-change-requests/", "POST", body, token)
        return JSONObject(text).optString("message")
    }

    private fun request(
        path: String,
        method: String,
        body: String? = null,
        token: String? = null,
    ): Pair<Int, String> {
        val connection = (URL(root + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 15_000
            readTimeout = 20_000
            setRequestProperty("Accept", "application/json")
            if (token != null) setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
        }
        val status = connection.responseCode
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.use { input ->
            BufferedReader(InputStreamReader(input, Charsets.UTF_8)).readText()
        } ?: ""
        connection.disconnect()
        if (status !in 200..299) throw refusal(status, text)
        return status to text
    }

    private fun refusal(status: Int, text: String): ApiException {
        val message = runCatching {
            val json = JSONObject(text)
            json.optString("error").ifEmpty { json.optString("detail") }
        }.getOrDefault("")
        val code = runCatching { JSONObject(text).optString("code") }.getOrDefault("")
        return ApiException(
            status,
            message.ifEmpty {
                if (status == 401) "انتهت الجلسة. سجّل الدخول من جديد."
                else "تعذّر الاتصال بالخادم ($status)."
            },
            code,
        )
    }
}

fun parseProfile(json: JSONObject): Profile {
    val pending = json.optJSONObject("pendingPhoneChange")
    return Profile(
        username = json.optString("username"),
        displayName = json.optString("displayName").ifEmpty { json.optString("username") },
        role = json.optString("role"),
        phone = json.optString("phone"),
        pendingPhone = pending?.optString("requestedPhone")?.takeIf { it.isNotEmpty() },
    )
}

/**
 * The one place the update decision is made.
 *
 * The server may also say `updateAvailable`, but the app decides from the
 * numbers it can see: a response that says "update" for a build the phone
 * already has must not open a dialog, and one that says "no update" for a
 * higher build must not hide it.
 */
data class UpdateInfo(
    val versionName: String,
    val versionCode: Int,
    val downloadUrl: String,
    val notes: String,
    val mandatory: Boolean,
    val sha256: String,
    val sizeBytes: Long,
) {
    fun isNewerThan(installedCode: Int): Boolean = versionCode > installedCode
}

fun parseVersionResponse(text: String): UpdateInfo? {
    val json = JSONObject(text)
    val latest = json.optJSONObject("latest") ?: return null
    val code = latest.optInt("versionCode", 0)
    val url = latest.optString("downloadUrl")
    // Without a build number there is nothing to compare, and without an
    // address there is nothing to install: either way, no update.
    if (code <= 0 || url.isEmpty()) return null
    return UpdateInfo(
        versionName = latest.optString("versionName", code.toString()),
        versionCode = code,
        downloadUrl = url,
        notes = latest.optString("notes", ""),
        mandatory = latest.optBoolean("mandatory", false),
        sha256 = latest.optString("sha256", "").lowercase(),
        sizeBytes = latest.optLong("sizeBytes", 0L),
    )
}
