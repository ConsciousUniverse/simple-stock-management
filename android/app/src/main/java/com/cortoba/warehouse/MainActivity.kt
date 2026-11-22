package com.cortoba.warehouse

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import com.cortoba.warehouse.databinding.ActivityMainBinding

/**
 * The signed-in screen: who you are, the two things you came to do, and the
 * gear that holds everything else.
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

        binding.newIssue.setOnClickListener { openDocument(DocumentDirection.OUT) }
        binding.newAddition.setOnClickListener { openDocument(DocumentDirection.IN) }
        binding.myDocuments.setOnClickListener {
            startActivity(Intent(this, DocumentsActivity::class.java))
        }
        binding.settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.versionFooter.text = getString(
            R.string.version_line, BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE
        )

        // The name is on the phone already; the server only refreshes it.
        renderName(session.displayName, "")
        loadProfile()
        loadSummary()
        // The silent check that actually delivers updates: a new build is
        // offered here, and the manual check lives behind the gear.
        checkForUpdate(showWhenCurrent = false)
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        if (session.isSignedIn) loadSummary()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun openDocument(direction: DocumentDirection) {
        // A fresh sheet each time: yesterday's draft must not appear in today's
        // document, and a half-filled one must not be sent by accident.
        DraftHolder.draft = null
        startActivity(
            Intent(this, NewDocumentActivity::class.java)
                .putExtra(NewDocumentActivity.EXTRA_DIRECTION, direction.wire)
        )
    }

    private fun handleIntent(intent: Intent?) {
        if (intent?.getBooleanExtra(EXTRA_CHECK_UPDATES, false) == true) {
            checkForUpdate(showWhenCurrent = false)
        }
    }

    // ---------------------------------------------------------------- profile

    private fun loadProfile() {
        val api = session.api()
        val token = session.token ?: return goToLogin()
        api.onWaking = { runOnUiThread { binding.progress.visibility = View.VISIBLE } }
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

    /** How much is waiting for a manager: the one number worth a card. */
    private fun loadSummary() {
        val api = session.api()
        val token = session.token ?: return
        Thread {
            val result = runCatching { api.documents(token) }
            runOnUiThread {
                result.onSuccess { documents ->
                    val pending = documents.count { it.status == "pending" }
                    binding.documentsSummary.text = if (documents.isEmpty()) {
                        getString(R.string.documents_summary_none)
                    } else {
                        getString(R.string.documents_summary, documents.size, pending)
                    }
                }
            }
        }.start()
    }

    private fun render(loaded: Profile) {
        renderName(loaded.displayName, roleLabel(loaded.role))
        binding.pending.visibility = if (loaded.pendingPhone != null) View.VISIBLE else View.GONE
        if (loaded.pendingPhone != null) {
            binding.pending.text = getString(R.string.pending_phone_change, loaded.pendingPhone)
        }
    }

    private fun renderName(name: String, role: String) {
        val shown = name.ifEmpty { getString(R.string.my_account) }
        binding.name.text = shown
        binding.role.text = role.ifEmpty { getString(R.string.role_user) }
        binding.avatar.text = shown.trim().firstOrNull()?.uppercase() ?: "؟"
    }

    private fun roleLabel(role: String): String = when (role) {
        "manager" -> getString(R.string.role_manager)
        "shop_user" -> getString(R.string.role_shop)
        "receive_mail" -> getString(R.string.role_receive)
        else -> getString(R.string.role_user)
    }

    // ----------------------------------------------------------------- update

    private fun checkForUpdate(showWhenCurrent: Boolean) {
        val api = session.api()
        Thread {
            val result = runCatching { api.version(BuildConfig.VERSION_CODE) }
            runOnUiThread {
                result.onSuccess { info ->
                    if (info != null && info.isNewerThan(BuildConfig.VERSION_CODE)) {
                        Updates.offer(this, info)
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

    // ------------------------------------------------------------------ misc

    private fun askForNotificationPermission() {
        if (android.os.Build.VERSION.SDK_INT < 33) return
        val granted = checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
        if (!granted) {
            ActivityCompat.requestPermissions(
                this, arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 101
            )
        }
    }

    private fun goToLogin() {
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
    }

    companion object {
        const val EXTRA_CHECK_UPDATES = "check_updates"
    }
}
