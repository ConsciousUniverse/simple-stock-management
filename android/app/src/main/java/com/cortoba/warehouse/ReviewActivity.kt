package com.cortoba.warehouse

import android.graphics.BitmapFactory
import android.os.Bundle
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.cortoba.warehouse.databinding.ActivityReviewBinding
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.io.File

/**
 * The page the operator reads before anything leaves the phone: the paper's
 * header, its photograph, every scanned line with ITS unit, and one button —
 * صرف or إضافة.
 *
 * Nothing is sent until that button is pressed, and the server still treats it
 * as a request: the balance moves only when a warehouse manager approves it.
 */
class ReviewActivity : AppCompatActivity() {

    private lateinit var binding: ActivityReviewBinding
    private lateinit var session: Session
    private lateinit var draft: DocumentDraft

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityReviewBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = Session(this)

        val current = DraftHolder.draft
        if (!session.isSignedIn || current == null) {
            finish()
            return
        }
        draft = current

        render()

        binding.submit.setOnClickListener { submit() }
        binding.back.setOnClickListener { finish() }
    }

    private fun render() {
        val isIssue = draft.direction == DocumentDirection.OUT
        binding.summary.text = getString(R.string.total_items, draft.itemCount, draft.totalQuantity)
        binding.submit.setText(if (isIssue) R.string.submit_issue else R.string.submit_addition)
        binding.dateValue.text = draft.dateIso
        binding.voucherValue.text = draft.voucher
        binding.locationValue.text = draft.location
        binding.engineerValue.text = draft.engineer
        binding.notesValue.text = draft.notes
        binding.notesValue.visibility = if (draft.notes.isBlank()) View.GONE else View.VISIBLE

        draft.photoPath?.let { path ->
            if (File(path).exists()) binding.photo.setImageBitmap(BitmapFactory.decodeFile(path))
        }

        binding.lines.removeAllViews()
        draft.lines.forEach { line ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, dp(6), 0, dp(6))
            }
            val name = TextView(this).apply {
                text = line.description.ifBlank { line.code }
                textSize = 15f
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            val amount = TextView(this).apply {
                text = if (line.unit.isBlank()) "${line.quantity}" else "${line.quantity} ${line.unit}"
                textSize = 15f
            }
            row.addView(name)
            row.addView(amount)
            binding.lines.addView(row)
        }
        binding.total.text = getString(R.string.total_items, draft.itemCount, draft.totalQuantity)
    }

    private fun submit() {
        val missing = draft.missing()
        if (missing != null) {
            finish() // back to the entry screen, which says what is missing
            return
        }
        val token = session.token ?: return finish()
        val api = session.api()
        binding.progress.visibility = View.VISIBLE
        binding.submit.isEnabled = false

        Thread {
            val result = runCatching { api.createDocument(token, draft) }
            runOnUiThread {
                binding.progress.visibility = View.GONE
                binding.submit.isEnabled = true
                result.onSuccess { document ->
                    DraftHolder.draft = null
                    MaterialAlertDialogBuilder(this)
                        .setTitle(R.string.document_sent)
                        .setMessage("${document.number}\n${getString(R.string.submit_explained)}")
                        .setPositiveButton(R.string.my_documents) { _, _ ->
                            startActivity(
                                android.content.Intent(this, DocumentsActivity::class.java)
                            )
                            finish()
                        }
                        .setNegativeButton(R.string.cancel) { _, _ -> finish() }
                        .show()
                }.onFailure { error ->
                    if (error is ApiException && error.status == 401) {
                        session.clear()
                        finish()
                        return@onFailure
                    }
                    // The server's own sentence: it names the code that is
                    // unknown, or the voucher already booked.
                    MaterialAlertDialogBuilder(this)
                        .setTitle(R.string.send_failed)
                        .setMessage(error.message)
                        .setPositiveButton(R.string.edit, null)
                        .show()
                }
            }
        }.start()
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()
}
