package com.cortoba.warehouse

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.cortoba.warehouse.databinding.ActivityNewDocumentBinding
import com.cortoba.warehouse.databinding.RowDraftLineBinding
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import java.util.UUID

/**
 * The warehouse flow, in the order the paper is filled in: the date, the
 * document number, where the goods go, the engineer who signed, then the
 * photograph of the signed sheet, then the items scanned off the shelves.
 *
 * The draft survives going to the review screen and coming back, so "edit"
 * never loses what was typed.
 */
class NewDocumentActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_DIRECTION = "direction"
        private const val MAX_PHOTO_PIXELS = 1600
        private const val PHOTO_QUALITY = 80
    }

    private lateinit var binding: ActivityNewDocumentBinding
    private lateinit var session: Session
    private lateinit var draft: DocumentDraft

    private var captureFile: File? = null
    private var pendingUri: Uri? = null

    private val takePicture =
        registerForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
            if (saved) {
                pendingUri?.let { compressAndAttach(it) }
            } else {
                toast(getString(R.string.photo_missing))
            }
        }

    private val askCamera =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) launchCamera() else toast(getString(R.string.camera_denied))
        }

    private val scan =
        registerForActivityResult(ScanContract()) { result ->
            val code = result.contents?.trim().orEmpty()
            if (code.isNotEmpty()) lookup(code)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityNewDocumentBinding.inflate(layoutInflater)
        setContentView(binding.root)
        session = Session(this)
        if (!session.isSignedIn) {
            finish()
            return
        }

        val direction = intent.getStringExtra(EXTRA_DIRECTION)
            ?.let { value -> DocumentDirection.entries.firstOrNull { it.wire == value } }
            ?: DocumentDirection.OUT

        // Coming back from the review screen must not empty the form.
        val kept = DraftHolder.draft
        draft = if (kept != null && kept.direction == direction) kept else DocumentDraft(direction)
        DraftHolder.draft = draft

        binding.title.setText(
            if (direction == DocumentDirection.OUT) R.string.issue_title else R.string.addition_title
        )

        restore()
        binding.dateButton.setOnClickListener { pickDate() }
        binding.takePhoto.setOnClickListener { requestCameraThenCapture() }
        binding.scan.setOnClickListener { startScan() }
        binding.typeCode.setOnClickListener { askForCode() }
        binding.review.setOnClickListener { goToReview() }
        renderLines()
        renderPhoto()
    }

    override fun onPause() {
        super.onPause()
        collect() // never lose what was typed if the phone is put away
    }

    // ------------------------------------------------------------------ header

    private fun restore() {
        binding.dateButton.text = draft.dateIso
        binding.voucher.setText(draft.voucher)
        binding.location.setText(draft.location)
        binding.engineer.setText(draft.engineer)
        binding.notes.setText(draft.notes)
    }

    private fun collect() {
        draft.voucher = binding.voucher.text?.toString().orEmpty().trim()
        draft.location = binding.location.text?.toString().orEmpty().trim()
        draft.engineer = binding.engineer.text?.toString().orEmpty().trim()
        draft.notes = binding.notes.text?.toString().orEmpty().trim()
    }

    private fun pickDate() {
        val calendar = Calendar.getInstance()
        runCatching {
            calendar.time = SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(draft.dateIso)!!
        }
        android.app.DatePickerDialog(
            this,
            { _, year, month, day ->
                calendar.set(year, month, day)
                draft.dateIso = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(calendar.time)
                binding.dateButton.text = draft.dateIso
            },
            calendar.get(Calendar.YEAR),
            calendar.get(Calendar.MONTH),
            calendar.get(Calendar.DAY_OF_MONTH),
        ).show()
    }

    // ------------------------------------------------------------------- photo

    private fun requestCameraThenCapture() {
        val granted = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        if (granted) launchCamera() else askCamera.launch(Manifest.permission.CAMERA)
    }

    private fun launchCamera() {
        val folder = File(filesDir, "vouchers").apply { mkdirs() }
        val file = File(folder, "capture-${UUID.randomUUID()}.jpg")
        captureFile = file
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        pendingUri = uri
        runCatching { takePicture.launch(uri) }
            .onFailure { toast(getString(R.string.camera_denied)) }
    }

    /**
     * A phone camera writes 4-8 MB. The server refuses anything over 6 MB, and
     * a site connection would take minutes to send it — so the photo is scaled
     * and re-compressed here, before it ever leaves the phone.
     */
    private fun compressAndAttach(uri: Uri) {
        binding.progress.visibility = View.VISIBLE
        Thread {
            val target = runCatching {
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
                var sample = 1
                while (maxOf(bounds.outWidth, bounds.outHeight) / sample > MAX_PHOTO_PIXELS) {
                    sample *= 2
                }
                val options = BitmapFactory.Options().apply { inSampleSize = sample }
                val bitmap = contentResolver.openInputStream(uri)?.use {
                    BitmapFactory.decodeStream(it, null, options)
                } ?: error("unreadable photo")
                val out = File(File(filesDir, "vouchers").apply { mkdirs() }, "voucher-${UUID.randomUUID()}.jpg")
                out.outputStream().use { stream ->
                    bitmap.compress(Bitmap.CompressFormat.JPEG, PHOTO_QUALITY, stream)
                }
                bitmap.recycle()
                captureFile?.delete()
                out
            }.getOrNull()

            runOnUiThread {
                binding.progress.visibility = View.GONE
                if (target == null) {
                    toast(getString(R.string.lookup_failed))
                    return@runOnUiThread
                }
                draft.photoPath = target.absolutePath
                renderPhoto()
            }
        }.start()
    }

    private fun renderPhoto() {
        val path = draft.photoPath
        if (path.isNullOrBlank() || !File(path).exists()) {
            binding.photoPreview.visibility = View.GONE
            binding.photoState.setText(R.string.photo_missing)
            binding.photoState.setTextColor(ContextCompat.getColor(this, R.color.accent))
            binding.takePhoto.setText(R.string.photograph_document)
            return
        }
        val bitmap = BitmapFactory.decodeFile(path)
        binding.photoPreview.setImageBitmap(bitmap)
        binding.photoPreview.visibility = View.VISIBLE
        binding.photoState.setText(R.string.photo_taken)
        binding.photoState.setTextColor(ContextCompat.getColor(this, R.color.brand))
        binding.takePhoto.setText(R.string.retake_photo)
    }

    // ------------------------------------------------------------------- items

    private fun startScan() {
        val options = ScanOptions().apply {
            setDesiredBarcodeFormats(ScanOptions.ALL_CODE_TYPES)
            setPrompt(getString(R.string.scan_barcode))
            setBeepEnabled(false)
            // Our own activity: portrait, and focusing continuously. Locking the
            // orientation here would ask for landscape.
            setOrientationLocked(false)
            setCaptureActivity(ScannerActivity::class.java)
        }
        runCatching { scan.launch(options) }
            .onFailure { askForCode() } // no camera: typing the code still works
    }

    private fun askForCode() {
        val input = TextInputEditText(this).apply {
            hint = getString(R.string.code_hint)
            setSingleLine()
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.enter_code)
            .setView(input)
            .setNegativeButton(R.string.cancel, null)
            .setPositiveButton(R.string.add_item) { _, _ ->
                val code = input.text?.toString().orEmpty().trim()
                if (code.isNotEmpty()) lookup(code)
            }
            .show()
    }

    private fun lookup(code: String) {
        binding.progress.visibility = View.VISIBLE
        val token = session.token ?: return
        val api = session.api()
        Thread {
            val result = runCatching { api.lookupItem(token, code) }
            runOnUiThread {
                binding.progress.visibility = View.GONE
                result.onSuccess { item ->
                    if (draft.direction == DocumentDirection.OUT && item.quantity <= 0) {
                        MaterialAlertDialogBuilder(this)
                            .setTitle(R.string.over_issue_blocked)
                            .setMessage(
                                getString(
                                    R.string.not_enough_stock,
                                    item.quantity,
                                    item.unit.ifBlank { getString(R.string.stock_none) },
                                )
                            )
                            .setPositiveButton(android.R.string.ok, null)
                            .show()
                        return@onSuccess
                    }
                    val line = draft.add(item)
                    if (line.exceedsShelf) {
                        // Put the draft back where it was: a scan that cannot
                        // be issued must not leave a quantity on the sheet.
                        line.quantity -= 1
                        if (line.quantity <= 0) draft.remove(line.code)
                        renderLines()
                        MaterialAlertDialogBuilder(this)
                            .setTitle(R.string.over_issue_blocked)
                            .setMessage(
                                getString(
                                    R.string.not_enough_stock,
                                    line.available ?: 0,
                                    line.unit,
                                )
                            )
                            .setPositiveButton(android.R.string.ok, null)
                            .show()
                        return@onSuccess
                    }
                    renderLines()
                    toast("${item.description} · ${item.unit}")
                }.onFailure { error ->
                    if (error is ApiException && error.status == 401) {
                        session.clear()
                        finish()
                        return@onFailure
                    }
                    // The server's sentence says WHICH code is unknown; keeping
                    // it is what lets the operator re-scan the right label.
                    MaterialAlertDialogBuilder(this)
                        .setTitle(R.string.lookup_failed)
                        .setMessage(error.message)
                        .setPositiveButton(R.string.enter_code) { _, _ -> askForCode() }
                        .setNegativeButton(R.string.cancel, null)
                        .show()
                }
            }
        }.start()
    }

    private fun renderLines() {
        binding.lines.removeAllViews()
        binding.empty.visibility = if (draft.lines.isEmpty()) View.VISIBLE else View.GONE
        draft.lines.forEach { line ->
            val row = RowDraftLineBinding.inflate(layoutInflater, binding.lines, false)
            row.lineTitle.text = line.description.ifBlank { line.code }
            row.lineMeta.text = buildString {
                append(line.code)
                if (line.unit.isNotBlank()) append(" · ").append(line.unit)
                if (line.available != null) {
                    append("  ·  ")
                    append(getString(R.string.available_stock, line.available!!, line.unit))
                }
            }
            row.lineMeta.setTextColor(
                androidx.core.content.ContextCompat.getColor(
                    this,
                    if (line.exceedsShelf) R.color.danger else R.color.text_muted,
                )
            )
            row.lineQty.text = line.quantity.toString()
            row.linePlus.setOnClickListener {
                if (line.exceedsShelf || line.quantity >= (line.available ?: Int.MAX_VALUE)) {
                    toast(
                        getString(
                            R.string.not_enough_stock,
                            line.available ?: 0,
                            line.unit,
                        )
                    )
                    return@setOnClickListener
                }
                draft.setQuantity(line.code, line.quantity + 1)
                renderLines()
            }
            row.lineMinus.setOnClickListener {
                if (line.quantity <= 1) {
                    draft.remove(line.code)
                } else {
                    draft.setQuantity(line.code, line.quantity - 1)
                }
                renderLines()
            }
            row.lineRemove.setOnClickListener {
                draft.remove(line.code)
                renderLines()
            }
            binding.lines.addView(row.root)
        }
        val hasLines = draft.lines.isNotEmpty()
        binding.total.visibility = if (hasLines) View.VISIBLE else View.GONE
        binding.total.text = getString(R.string.total_items, draft.itemCount, draft.totalQuantity)
    }

    // ------------------------------------------------------------------ review

    private fun goToReview() {
        collect()
        val missing = draft.missing()
        if (missing != null) {
            toast(getString(R.string.required_field, missingLabel(missing)))
            return
        }
        draft.overIssued()?.let { line ->
            toast(getString(R.string.not_enough_stock, line.available ?: 0, line.unit))
            return
        }
        startActivity(Intent(this, ReviewActivity::class.java))
    }

    private fun missingLabel(field: MissingField): String = getString(
        when (field) {
            MissingField.DATE -> R.string.document_date
            MissingField.VOUCHER -> R.string.voucher_number
            MissingField.LOCATION -> R.string.location_label
            MissingField.ENGINEER -> R.string.engineer_label
            MissingField.PHOTO -> R.string.photograph_document
            MissingField.LINES -> R.string.items_title
        }
    )

    private fun toast(message: String) =
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
}

/** The draft between the entry screen and the review screen (one at a time). */
object DraftHolder {
    var draft: DocumentDraft? = null
}
