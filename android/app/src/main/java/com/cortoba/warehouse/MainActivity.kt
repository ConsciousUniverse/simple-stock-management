package com.cortoba.warehouse

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import com.cortoba.warehouse.databinding.ActivityMainBinding
import java.io.File

/**
 * The signed-in screen: who you are, the number you sign in with (read-only),
 * and the update prompt.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var session: Session
    private var profile: Profile? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = Session(this)

        if (!session.isSignedIn) {
            goToLogin()
            return
        }

        UpdateNotifier.ensureChannel(this)
        askForNotificationPermission()
        UpdateWorker.schedule(this)

        binding.signOut.setOnClickListener { signOut() }
        binding.requestPhoneChange.setOnClickListener { askForNewPhone() }
        binding.checkUpdates.setOnClickListener { checkForUpdate(showWhenCurrent = true) }
        binding.refresh.setOnClickListener { loadProfile() }

        loadProfile()
        checkForUpdate(showWhenCurrent = false)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent?.getBooleanExtra(EXTRA_CHECK_UPDATES, false) == true) {
            checkForUpdate(showWhenCurrent = false)
        }
    }

    // ---------------------------------------------------------------- profile

    private fun loadProfile() {
        binding.progress.visibility = View.VISIBLE
        val api = session.api()
        val token = session.token ?: return goToLogin()
        Thread {
            val result = runCatching { api.me(token) }
            runOnUiThread {
                binding.progress.visibility = View.GONE
                result.onSuccess { loaded ->
                    profile = loaded
                    session.remember(loaded)
                    render(loaded)
                }.onFailure { error ->
                    if (error is ApiException && error.status == 401) {
                        session.clear()
                        goToLogin()
                    } else {
                        Toast.makeText(
                            this,
                            error.message ?: getString(R.string.sign_in_failed),
                            Toast.LENGTH_LONG,
                        ).show()
                    }
                }
            }
        }.start()
    }

    private fun render(loaded: Profile) {
        binding.name.text = loaded.displayName
        binding.role.text = roleLabel(loaded.role)
        binding.phone.text = loaded.phone.ifEmpty { getString(R.string.no_phone) }
        binding.phoneLock.visibility = View.VISIBLE
        binding.pending.visibility = if (loaded.pendingPhone != null) View.VISIBLE else View.GONE
        if (loaded.pendingPhone != null) {
            binding.pending.text = getString(R.string.pending_phone_change, loaded.pendingPhone)
        }
    }

    private fun roleLabel(role: String): String = when (role) {
        "manager" -> getString(R.string.role_manager)
        "shop_user" -> getString(R.string.role_shop)
        "receive_mail" -> getString(R.string.role_receive)
        else -> getString(R.string.role_user)
    }

    private fun askForNewPhone() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_PHONE
            hint = getString(R.string.new_phone_hint)
        }
        val reason = EditText(this).apply {
            hint = getString(R.string.new_phone_reason)
            setSingleLine(false)
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 16, 48, 0)
            addView(input)
            addView(reason)
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.request_phone_change)
            .setMessage(R.string.request_phone_change_explained)
            .setView(container)
            .setPositiveButton(R.string.send_request) { _, _ ->
                submitPhoneChange(input.text.toString().trim(), reason.text.toString().trim())
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun submitPhoneChange(newPhone: String, reason: String) {
        if (newPhone.isEmpty()) {
            Toast.makeText(this, R.string.phone_and_password_required, Toast.LENGTH_LONG).show()
            return
        }
        val api = session.api()
        val token = session.token ?: return
        Thread {
            val result = runCatching { api.requestPhoneChange(token, newPhone, reason) }
            runOnUiThread {
                result.onSuccess { message ->
                    Toast.makeText(
                        this,
                        message.ifEmpty { getString(R.string.request_sent) },
                        Toast.LENGTH_LONG,
                    ).show()
                    loadProfile()
                }.onFailure { error ->
                    Toast.makeText(
                        this,
                        error.message ?: getString(R.string.sign_in_failed),
                        Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }.start()
    }

    // ----------------------------------------------------------------- update

    private fun checkForUpdate(showWhenCurrent: Boolean) {
        val api = session.api()
        Thread {
            val result = runCatching { api.version(BuildConfig.VERSION_CODE) }
            runOnUiThread {
                result.onSuccess { info ->
                    if (info != null && info.isNewerThan(BuildConfig.VERSION_CODE)) {
                        showUpdate(info)
                    } else if (showWhenCurrent) {
                        Toast.makeText(
                            this,
                            getString(R.string.already_current, BuildConfig.VERSION_NAME),
                            Toast.LENGTH_SHORT,
                        ).show()
                    }
                }.onFailure {
                    if (showWhenCurrent) {
                        Toast.makeText(
                            this,
                            getString(R.string.update_check_failed),
                            Toast.LENGTH_LONG,
                        ).show()
                    }
                }
            }
        }.start()
    }

    /**
     * The dialog the operator asked for. A mandatory build has no "later": the
     * whole point of the flag is a client that can no longer talk to the server.
     */
    private fun showUpdate(info: UpdateInfo) {
        val builder = AlertDialog.Builder(this)
            .setTitle(getString(R.string.update_available_title))
            .setMessage(
                buildString {
                    append(getString(R.string.update_available_body, info.versionName))
                    if (info.notes.isNotBlank()) {
                        append("\n\n")
                        append(info.notes)
                    }
                    if (info.mandatory) {
                        append("\n\n")
                        append(getString(R.string.update_mandatory_note))
                    }
                }
            )
            .setPositiveButton(R.string.update_now) { _, _ -> downloadAndInstall(info) }
            .setCancelable(!info.mandatory)

        if (!info.mandatory) {
            builder.setNegativeButton(R.string.later, null)
        }
        builder.show()
    }

    private fun downloadAndInstall(info: UpdateInfo) {
        if (!Apk.canInstall(this)) {
            Toast.makeText(this, R.string.allow_install_explained, Toast.LENGTH_LONG).show()
            Apk.openInstallPermission(this)
            return
        }

        val target = Apk.targetFile(this, info)
        val progress = android.widget.ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            setPadding(48, 32, 48, 32)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.downloading_update)
            .setView(progress)
            .setCancelable(false)
            .create()
        dialog.show()

        Thread {
            val result = runCatching {
                Apk.download(info.downloadUrl, target) { percent ->
                    runOnUiThread { progress.progress = percent }
                }
                if (!Apk.checksumMatches(target, info.sha256)) {
                    target.delete()
                    throw IllegalStateException(getString(R.string.checksum_mismatch))
                }
                target
            }
            runOnUiThread {
                dialog.dismiss()
                result.onSuccess { file ->
                    UpdateNotifier.clear(this)
                    Apk.install(this, file)
                }.onFailure { error ->
                    Toast.makeText(
                        this,
                        error.message ?: getString(R.string.update_check_failed),
                        Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }.start()
    }

    // ------------------------------------------------------------------- misc

    private fun askForNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(android.Manifest.permission.POST_NOTIFICATIONS),
                REQUEST_NOTIFICATIONS,
            )
        }
    }

    private fun signOut() {
        val api = session.api()
        val token = session.token
        session.clear()
        Thread {
            runCatching { token?.let { api.logout(it) } }
        }.start()
        goToLogin()
    }

    private fun goToLogin() {
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
    }

    companion object {
        const val EXTRA_CHECK_UPDATES = "check_updates"
        private const val REQUEST_NOTIFICATIONS = 91
    }
}
