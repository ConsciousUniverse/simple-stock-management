package com.cortoba.warehouse

import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.cortoba.warehouse.databinding.ActivityDocumentsBinding
import com.cortoba.warehouse.databinding.RowDocumentBinding

/**
 * What happened to what the operator sent: waiting, approved, or rejected with
 * the manager's note. Without this screen the phone sends a document into a
 * void — the operator has no way to know whether it moved the stock.
 */
class DocumentsActivity : AppCompatActivity() {

    private lateinit var binding: ActivityDocumentsBinding
    private lateinit var session: Session

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDocumentsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = Session(this)
        if (!session.isSignedIn) {
            finish()
            return
        }
    }

    override fun onResume() {
        super.onResume()
        load()
    }

    private fun load() {
        val token = session.token ?: return
        val api = session.api()
        binding.progress.visibility = View.VISIBLE
        Thread {
            val result = runCatching { api.documents(token) }
            runOnUiThread {
                binding.progress.visibility = View.GONE
                result.onSuccess { documents ->
                    binding.rows.removeAllViews()
                    binding.empty.visibility =
                        if (documents.isEmpty()) View.VISIBLE else View.GONE
                    documents.forEach { binding.rows.addView(row(it)) }
                }.onFailure { error ->
                    if (error is ApiException && error.status == 401) {
                        session.clear()
                        finish()
                        return@onFailure
                    }
                    binding.empty.visibility = View.VISIBLE
                    binding.empty.text = error.message
                }
            }
        }.start()
    }

    private fun row(document: SubmittedDocument): View {
        val row = RowDocumentBinding.inflate(layoutInflater, binding.rows, false)
        row.number.text = document.number
        row.status.text = when (document.status) {
            "approved" -> getString(R.string.status_approved)
            "rejected" -> getString(R.string.status_rejected)
            else -> getString(R.string.status_pending)
        }
        val (textColour, background) = when (document.status) {
            "approved" -> R.color.success to R.drawable.bg_pill_success
            "rejected" -> R.color.danger to R.drawable.bg_pill_danger
            else -> R.color.warn to R.drawable.bg_pill_warn
        }
        row.status.setTextColor(ContextCompat.getColor(this, textColour))
        row.status.setBackgroundResource(background)

        row.meta.text = buildString {
            append(document.documentDate)
            if (document.location.isNotBlank()) append(" · ").append(document.location)
            if (document.engineerName.isNotBlank()) append(" · ").append(document.engineerName)
            append(" · ").append(getString(R.string.total_items, document.itemCount, document.quantity))
        }
        row.decision.visibility = if (document.decisionNote.isBlank()) View.GONE else View.VISIBLE
        row.decision.text = document.decisionNote
        return row.root
    }
}
