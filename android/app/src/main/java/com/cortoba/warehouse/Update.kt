package com.cortoba.warehouse

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.NotificationCompat
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Downloading and installing the new build.
 *
 * The checksum is checked BEFORE the installer is opened: an APK whose bytes do
 * not match the published hash is refused, because installing it would hand the
 * phone to whoever produced it.
 */
object Apk {

    fun targetFile(context: Context, info: UpdateInfo): File {
        val directory = File(context.getExternalFilesDir(null), "updates").apply { mkdirs() }
        // One file per build, so a half-downloaded older build cannot be
        // mistaken for the new one.
        return File(directory, "warehouse-${info.versionCode}.apk")
    }

    fun download(
        url: String,
        target: File,
        onProgress: (percent: Int) -> Unit = {},
    ): File {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 20_000
            readTimeout = 60_000
            setRequestProperty("Accept", "application/octet-stream")
        }
        try {
            val status = connection.responseCode
            if (status !in 200..299) {
                throw IllegalStateException("تعذّر تنزيل التحديث ($status).")
            }
            val total = connection.contentLengthLong
            connection.inputStream.use { input ->
                FileOutputStream(target).use { output ->
                    val buffer = ByteArray(64 * 1024)
                    var written = 0L
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        written += read
                        if (total > 0) onProgress(((written * 100) / total).toInt())
                    }
                }
            }
        } finally {
            connection.disconnect()
        }
        return target
    }

    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /** True when the file is what the server published, or when no hash was published. */
    fun checksumMatches(file: File, expected: String): Boolean {
        if (expected.isBlank()) return true
        return sha256(file).equals(expected.trim().lowercase(), ignoreCase = true)
    }

    fun canInstall(context: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.packageManager.canRequestPackageInstalls()
        } else {
            true
        }

    fun openInstallPermission(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
                .setData(Uri.parse("package:${context.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            runCatching { context.startActivity(intent) }
        }
    }

    fun install(context: Context, file: File) {
        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            file,
        )
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.startActivity(intent)
    }
}

/**
 * The notification the operator asked for: "a new version is available".
 *
 * A notification is not the same promise as a dialog — it says a build exists
 * and opens the app where the install can be done, which is what a warehouse
 * phone needs when the app is closed.
 */
object UpdateNotifier {

    const val CHANNEL_ID = "app_updates"
    const val NOTIFICATION_ID = 4711

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.update_channel_name),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = context.getString(R.string.update_channel_description)
        }
        manager.createNotificationChannel(channel)
    }

    fun notify(context: Context, info: UpdateInfo) {
        ensureChannel(context)
        val open = Intent(context, MainActivity::class.java)
            .putExtra(MainActivity.EXTRA_CHECK_UPDATES, true)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val pending = PendingIntent.getActivity(
            context,
            0,
            open,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification: Notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_update)
            .setContentTitle(context.getString(R.string.update_available_title))
            .setContentText(
                context.getString(R.string.update_available_body, info.versionName)
            )
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    if (info.notes.isBlank()) {
                        context.getString(R.string.update_available_body, info.versionName)
                    } else {
                        info.notes
                    }
                )
            )
            .setPriority(if (info.mandatory) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
            .setOngoing(info.mandatory)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()
        runCatching {
            context.getSystemService(NotificationManager::class.java)
                .notify(NOTIFICATION_ID, notification)
        }
    }

    fun clear(context: Context) {
        runCatching {
            context.getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
        }
    }
}
