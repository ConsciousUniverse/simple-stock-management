package com.cortoba.warehouse

import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID

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

    /**
     * Called when a request had to be retried because the server was not
     * answering yet — Render stops an idle service, and the first request
     * after fifteen quiet minutes wakes it. The screen says so instead of
     * showing a failure the operator would read as "the app is broken".
     */
    var onWaking: (() -> Unit)? = null

    /** How many times a connection-level failure is retried, and how long to wait. */
    private val wakeDelaysMs = longArrayOf(2_000, 3_000, 4_000, 6_000, 8_000, 10_000)

    fun version(installedCode: Int): UpdateInfo? =
        parseVersionResponse(
            request("api/mobile/version/?code=$installedCode", "GET").second
        )

    fun versionAnonymous(): UpdateInfo? =
        parseVersionResponse(request("api/mobile/version/", "GET").second)

    /** Repeating a sign-in is harmless: it only opens a session. */
    fun login(
        phone: String,
        password: String,
        device: String,
        deviceId: String,
    ): Pair<String, Profile> {
        val body = JSONObject()
            .put("phone", phone)
            .put("password", password)
            .put("device", device)
            .put("deviceId", deviceId)
            .toString()
        // Repeatable: a second sign-in only opens another session.
        val (_, text) = request("api/mobile/login/", "POST", body, repeatable = true)
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

    /**
     * What a scanned label is: its description and — the point of the lookup —
     * the unit the catalogue counts it in.
     */
    fun lookupItem(token: String, code: String): ItemInfo {
        val encoded = URLEncoder.encode(code, "UTF-8")
        val (_, text) = request("api/mobile/items/lookup/?code=$encoded", "GET", null, token)
        return parseItem(JSONObject(text).getJSONObject("item"))
    }

    /** Send the finished document, with its photographed voucher. */
    fun createDocument(token: String, draft: DocumentDraft): SubmittedDocument {
        val photo = draft.photoPath?.let { File(it) }
        val (_, text) = multipart(
            path = "api/mobile/documents/",
            token = token,
            fields = draft.fields(),
            file = photo,
            fileField = "photo",
            mimeType = "image/jpeg",
        )
        return parseDocument(JSONObject(text).getJSONObject("document"))
    }

    /** The documents this user sent, newest first, with their outcome. */
    fun documents(token: String): List<SubmittedDocument> =
        parseDocuments(request("api/mobile/documents/", "GET", null, token).second)

    /**
     * A multipart body written by hand: the photograph and the fields it
     * belongs to must arrive in one request, or a document could be saved
     * without the paper behind it.
     */
    private fun multipart(
        path: String,
        token: String,
        fields: Map<String, String>,
        file: File?,
        fileField: String,
        mimeType: String,
    ): Pair<Int, String> =
        retrying(false) { multipartOnce(path, token, fields, file, fileField, mimeType) }

    private fun multipartOnce(
        path: String,
        token: String,
        fields: Map<String, String>,
        file: File?,
        fileField: String,
        mimeType: String,
    ): Pair<Int, String> {
        val boundary = "----warehouse-${UUID.randomUUID()}"
        val connection = (URL(root + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 20_000
            // A photograph on a site connection is slower than a JSON call.
            readTimeout = 90_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            doOutput = true
        }

        fun OutputStream.text(value: String) = write(value.toByteArray(Charsets.UTF_8))

        connection.outputStream.use { output ->
            fields.forEach { (name, value) ->
                output.text("--$boundary\r\n")
                output.text("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
                output.text(value)
                output.text("\r\n")
            }
            if (file != null && file.exists()) {
                output.text("--$boundary\r\n")
                output.text(
                    "Content-Disposition: form-data; name=\"$fileField\"; filename=\"${file.name}\"\r\n"
                )
                output.text("Content-Type: $mimeType\r\n\r\n")
                file.inputStream().use { it.copyTo(output) }
                output.text("\r\n")
            }
            output.text("--$boundary--\r\n")
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

    private fun request(
        path: String,
        method: String,
        body: String? = null,
        token: String? = null,
        repeatable: Boolean = false,
    ): Pair<Int, String> = retrying(method == "GET" || repeatable) {
        requestOnce(path, method, body, token)
    }

    /**
     * Run a call, waking the server if it is asleep.
     *
     * A stopped Render service does not answer with an error the operator can
     * act on: the connection is refused, or the proxy answers 502/503 while
     * the instance boots. Both mean "try again in a moment", and the app has
     * to do the retrying itself — nobody is going to press the button again.
     * A refusal from the API (401, 400, 409…) is NOT retried: it is an answer.
     */
    private fun retrying(repeatable: Boolean, call: () -> Pair<Int, String>): Pair<Int, String> {
        var last: Exception? = null
        for (attempt in 0..wakeDelaysMs.size) {
            try {
                return call()
            } catch (error: Exception) {
                if (!Retry.shouldRetry(repeatable, error, attempt, wakeDelaysMs.size)) throw error
                last = error
            }
            onWaking?.invoke()
            Thread.sleep(wakeDelaysMs[attempt])
        }
        throw last ?: java.io.IOException("تعذّر الاتصال بالخادم.")
    }

    private fun requestOnce(
        path: String,
        method: String,
        body: String? = null,
        token: String? = null,
    ): Pair<Int, String> {
        val connection = (URL(root + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            // A sleeping service needs time to accept the connection at all,
            // and the first query after a cold start is slower than a warm one.
            connectTimeout = 20_000
            readTimeout = 60_000
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
