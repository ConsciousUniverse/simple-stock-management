package com.cortoba.warehouse

import android.app.Activity
import android.widget.ProgressBar
import android.widget.Toast
import androidx.appcompat.app.AlertDialog

/**
 * The update prompt, in one place.
 *
 * Both the dashboard (silent check on open) and the settings screen (the
 * manual check) end here, so a new build is offered the same way whichever
 * door the person came through.
 */
object Updates {

    /**
     * A mandatory build has no "later": the whole point of the flag is a
     * client that can no longer talk to the server.
     */
    fun offer(activity: Activity, info: UpdateInfo) {
        val builder = AlertDialog.Builder(activity)
            .setTitle(activity.getString(R.string.update_available_title))
            .setMessage(
                buildString {
                    append(activity.getString(R.string.update_available_body, info.versionName))
                    if (info.notes.isNotBlank()) {
                        append("\n\n")
                        append(info.notes)
                    }
                    if (info.mandatory) {
                        append("\n\n")
                        append(activity.getString(R.string.update_mandatory_note))
                    }
                }
            )
            .setPositiveButton(R.string.update_now) { _, _ -> downloadAndInstall(activity, info) }
            .setCancelable(!info.mandatory)

        if (!info.mandatory) {
            builder.setNegativeButton(R.string.later, null)
        }
        builder.show()
    }

    private fun downloadAndInstall(activity: Activity, info: UpdateInfo) {
        if (!Apk.canInstall(activity)) {
            Toast.makeText(
                activity, R.string.allow_install_explained, Toast.LENGTH_LONG
            ).show()
            Apk.openInstallPermission(activity)
            return
        }

        val target = Apk.targetFile(activity, info)
        val progress = ProgressBar(
            activity, null, android.R.attr.progressBarStyleHorizontal
        ).apply {
            max = 100
            setPadding(48, 32, 48, 32)
        }
        val dialog = AlertDialog.Builder(activity)
            .setTitle(R.string.downloading_update)
            .setView(progress)
            .setCancelable(false)
            .create()
        dialog.show()

        Thread {
            val result = runCatching {
                Apk.download(info.downloadUrl, target) { percent ->
                    activity.runOnUiThread { progress.progress = percent }
                }
                if (!Apk.checksumMatches(target, info.sha256)) {
                    target.delete()
                    throw IllegalStateException(activity.getString(R.string.checksum_mismatch))
                }
                target
            }
            activity.runOnUiThread {
                dialog.dismiss()
                result.onSuccess { file ->
                    UpdateNotifier.clear(activity)
                    Apk.install(activity, file)
                }.onFailure { error ->
                    Toast.makeText(
                        activity,
                        error.message ?: activity.getString(R.string.update_check_failed),
                        Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }.start()
    }
}
