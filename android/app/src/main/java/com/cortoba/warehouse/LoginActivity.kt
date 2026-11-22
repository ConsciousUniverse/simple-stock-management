package com.cortoba.warehouse

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.cortoba.warehouse.databinding.ActivityLoginBinding

/**
 * Signing in, in one field.
 *
 * The account stays on the phone it was first opened on — the server binds it
 * to a device id — so asking for the phone number every morning is asking for
 * something the app already knows. The identifier field appears only when the
 * person asks for another account.
 */
class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private lateinit var session: Session

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = Session(this)

        session.forgetStoredServer()
        binding.versionLabel.text = getString(
            R.string.version_line, BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE
        )

        binding.signIn.setOnClickListener { signIn() }
        binding.switchAccount.setOnClickListener { showIdentifierField() }
        binding.forgotPhone.setOnClickListener {
            Toast.makeText(this, R.string.forgot_phone_hint, Toast.LENGTH_LONG).show()
        }
        binding.passwordInput.setOnEditorActionListener { _, _, _ ->
            signIn()
            true
        }

        // A remembered account signs in with the password alone.
        val remembered = session.phone
        if (remembered.isEmpty()) {
            showIdentifierField()
        } else {
            // The name only: the number is the account's business, not the
            // business of whoever is looking over the shoulder.
            val name = session.displayName.ifEmpty { getString(R.string.role_user) }
            binding.welcomeTitle.text = getString(R.string.welcome_back)
            binding.welcomeAccount.text = name
        }

        if (session.isSignedIn) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }
    }

    private fun showIdentifierField() {
        binding.phoneBox.visibility = View.VISIBLE
        binding.welcomeTitle.setText(R.string.sign_in_title)
        binding.welcomeAccount.setText(R.string.sign_in_subtitle)
        binding.switchAccount.visibility = View.GONE
        binding.phoneInput.setText(session.phone)
        binding.passwordInput.requestFocus()
    }

    private fun signIn() {
        val phone = binding.phoneInput.text?.toString()?.trim().orEmpty()
            .ifEmpty { session.phone }
        val password = binding.passwordInput.text?.toString().orEmpty()

        if (phone.isEmpty()) {
            showIdentifierField()
            showError(getString(R.string.phone_and_password_required))
            return
        }
        if (password.isEmpty()) {
            showError(getString(R.string.password_required))
            return
        }

        setBusy(true)
        val api = session.api()
        api.onWaking = { runOnUiThread { binding.waking.visibility = View.VISIBLE } }
        Thread {
            val result = runCatching {
                api.login(phone, password, session.deviceLabel(), session.deviceId)
            }
            runOnUiThread {
                setBusy(false)
                binding.waking.visibility = View.GONE
                result.onSuccess { (token, profile) ->
                    session.token = token
                    session.remember(profile)
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                }.onFailure { error -> showFailure(error) }
            }
        }.start()
    }

    /**
     * A refusal is shown as the server wrote it: "the account is on another
     * phone (Samsung A12)" is a sentence the person can take to their manager,
     * and a generic "sign-in failed" is not.
     */
    private fun showFailure(error: Throwable) {
        if (error is ApiException && error.code == "device_locked") {
            AlertDialog.Builder(this)
                .setTitle(R.string.device_locked_title)
                .setMessage(error.message)
                .setPositiveButton(android.R.string.ok, null)
                .show()
            return
        }
        showError(error.message ?: getString(R.string.sign_in_failed))
    }

    private fun setBusy(busy: Boolean) {
        binding.signIn.isEnabled = !busy
        binding.signIn.text =
            if (busy) getString(R.string.server_waking_status) else getString(R.string.sign_in)
        binding.progress.visibility = if (busy) View.VISIBLE else View.GONE
        binding.error.visibility = View.GONE
    }

    private fun showError(message: String) {
        binding.error.text = message
        binding.error.visibility = View.VISIBLE
    }
}
