package com.cortoba.warehouse

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.cortoba.warehouse.databinding.ActivityLoginBinding

/**
 * Signing in: the phone number and the password a manager gave.
 *
 * The phone is the identity and the app cannot change it — the sign-in screen
 * has no "change my number" field, because there is nothing it could do with
 * one. A new number is asked for from the profile screen and approved by a
 * warehouse manager.
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
        binding.phoneInput.setText(session.phone)
        binding.signIn.setOnClickListener { signIn() }
        binding.forgotPhone.setOnClickListener {
            Toast.makeText(this, R.string.forgot_phone_hint, Toast.LENGTH_LONG).show()
        }

        if (session.isSignedIn) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }
    }

    private fun signIn() {
        val phone = binding.phoneInput.text?.toString()?.trim().orEmpty()
        val password = binding.passwordInput.text?.toString().orEmpty()

        if (phone.isEmpty() || password.isEmpty()) {
            showError(getString(R.string.phone_and_password_required))
            return
        }

        setBusy(true)
        val api = session.api()
        Thread {
            val result = runCatching {
                api.login(phone, password, "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}")
            }
            runOnUiThread {
                setBusy(false)
                result.onSuccess { (token, profile) ->
                    session.token = token
                    session.remember(profile)
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                }.onFailure { error ->
                    showError(error.message ?: getString(R.string.sign_in_failed))
                }
            }
        }.start()
    }

    private fun setBusy(busy: Boolean) {
        binding.signIn.isEnabled = !busy
        binding.progress.visibility = if (busy) android.view.View.VISIBLE else android.view.View.GONE
    }

    private fun showError(message: String) {
        binding.error.text = message
        binding.error.visibility = android.view.View.VISIBLE
    }
}
