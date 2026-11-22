package com.cortoba.warehouse

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.cortoba.warehouse.databinding.ActivitySettingsBinding

/**
 * The gear: who you are, what build you are on, whether the server is awake,
 * and the way out.
 *
 * The update check lives here rather than on the dashboard so the screen a
 * person uses every day stays two buttons and a count.
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding
    private lateinit var session: Session

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = Session(this)

        binding.back.setOnClickListener { finish() }
        binding.signOut.setOnClickListener { confirmSignOut() }
        binding.requestPhoneChange.setOnClickListener { askForNewPhone() }
        binding.checkUpdates.setOnClickListener { checkForUpdate() }
        binding.testServer.setOnClickListener { testServer() }

        binding.versionLabel.text = getString(
            R.string.version_line, BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE
        )
        binding.deviceLine.text = getString(R.string.device_line, session.deviceLabel())
        binding.accountName.text =
            session.displayName.ifEmpty { getString(R.string.my_account) }
        binding.accountPhone.text = session.maskedPhone.ifEmpty { getString(R.string.no_phone) }
        binding.serverStatus.setText(R.string.server_online)
        loadProfile()
    }

    private fun loadProfile() {
        val api = session.api()
        val token = session.token ?: return
        Thread {
            val result = runCatching { api.me(token) }
            runOnUiThread {
                result.onSuccess { profile ->
                    binding.accountName.text = profile.displayName
                    binding.accountRole.text = roleLabel(profile.role)
                    binding.accountPhone.text =
                        session.maskedPhone.ifEmpty { getString(R.string.no_phone) }
                    if (profile.pendingPhone != null) {
                        binding.accountPhone.append(
                            "\n" + getString(R.string.pending_phone_change, profile.pendingPhone)
                        )
                    }
                }.onFailure {
                    binding.serverStatus.setText(R.string.server_offline)
                }
            }
        }.start()
    }

    private fun roleLabel(role: String): String = when (role) {
        "manager" -> getString(R.string.role_manager)
        "shop_user" -> getString(R.string.role_shop)
        "receive_mail" -> getString(R.string.role_receive)
        else -> getString(R.string.role_user)
    }

    private fun checkForUpdate() {
        binding.updateStatus.setText(R.string.server_waking_status)
        val api = session.api()
        Thread {
            val result = runCatching { api.version(BuildConfig.VERSION_CODE) }
            runOnUiThread {
                result.onSuccess { info ->
                    if (info != null && info.isNewerThan(BuildConfig.VERSION_CODE)) {
                        binding.updateStatus.setText(R.string.update_auto_explained)
                        Updates.offer(this, info)
                    } else {
                        binding.updateStatus.text = getString(
                            R.string.already_current, BuildConfig.VERSION_NAME
                        )
                    }
                }.onFailure {
                    binding.updateStatus.setText(R.string.update_check_failed)
                }
            }
        }.start()
    }

    /**
     * Touch the server once and say what happened. The point is to show that a
     * sleeping service answers after a wait, instead of the person concluding
     * the app is broken.
     */
    private fun testServer() {
        binding.serverStatus.setText(R.string.server_waking_status)
        val api = session.api()
        api.onWaking = {
            runOnUiThread { binding.serverStatus.setText(R.string.server_waking_status) }
        }
        Thread {
            val result = runCatching { api.versionAnonymous() }
            runOnUiThread {
                binding.serverStatus.setText(
                    if (result.isSuccess) R.string.server_online else R.string.server_offline
                )
            }
        }.start()
    }

    private fun confirmSignOut() {
        AlertDialog.Builder(this)
            .setTitle(R.string.sign_out)
            .setMessage(R.string.sign_out_confirm)
            .setPositiveButton(R.string.sign_out) { _, _ -> signOut() }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun signOut() {
        val api = session.api()
        val token = session.token
        // The account stays remembered (the phone is bound to it); only the
        // session goes, so the next sign-in is the password alone.
        session.token = null
        Thread { runCatching { token?.let { api.logout(it) } } }.start()
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
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
}
