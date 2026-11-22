package com.cortoba.warehouse

import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/**
 * The document a site user is filling in: the paper's header, its photograph,
 * and the items scanned off the shelves.
 *
 * The rules live here rather than in a screen so they can be tested without a
 * phone, and so the entry screen and the review screen cannot disagree about
 * what is missing.
 */
enum class DocumentDirection(val wire: String) {
    /** Goods leave the warehouse: صرف. */
    OUT("out"),

    /** Goods come back to the warehouse: إضافة. */
    IN("in"),
}

/** What a scanned label resolved to. The unit is the catalogue's. */
data class ItemInfo(
    val code: String,
    val description: String,
    val unit: String,
    val quantity: Int,
    val price: String,
)

data class DraftLine(
    val code: String,
    val description: String,
    val unit: String,
    var quantity: Int,
)

/** The first thing standing between the draft and the server. */
enum class MissingField { DATE, VOUCHER, LOCATION, ENGINEER, PHOTO, LINES }

fun todayIso(): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Calendar.getInstance().time)

class DocumentDraft(val direction: DocumentDirection) {

    var dateIso: String = todayIso()
    var voucher: String = ""
    var location: String = ""
    var engineer: String = ""
    var notes: String = ""
    var photoPath: String? = null

    private val entries = mutableListOf<DraftLine>()

    val lines: List<DraftLine> get() = entries
    val itemCount: Int get() = entries.size
    val totalQuantity: Int get() = entries.sumOf { it.quantity }

    /**
     * Scanning the same label twice is a quantity of two, not two lines: the
     * paper lists the article once.
     */
    fun add(item: ItemInfo, quantity: Int = 1): DraftLine {
        val amount = if (quantity > 0) quantity else 1
        val existing = entries.firstOrNull { it.code == item.code }
        if (existing != null) {
            existing.quantity += amount
            return existing
        }
        val line = DraftLine(
            code = item.code,
            description = item.description,
            unit = item.unit,
            quantity = amount,
        )
        entries.add(line)
        return line
    }

    fun setQuantity(code: String, quantity: Int) {
        val line = entries.firstOrNull { it.code == code } ?: return
        line.quantity = if (quantity > 0) quantity else 1
    }

    fun remove(code: String) {
        entries.removeAll { it.code == code }
    }

    fun clear() {
        entries.clear()
    }

    /** The first missing thing, in the order the operator fills the screen. */
    fun missing(): MissingField? = when {
        dateIso.isBlank() -> MissingField.DATE
        voucher.isBlank() -> MissingField.VOUCHER
        location.isBlank() -> MissingField.LOCATION
        engineer.isBlank() -> MissingField.ENGINEER
        photoPath.isNullOrBlank() -> MissingField.PHOTO
        entries.isEmpty() -> MissingField.LINES
        else -> null
    }

    fun isComplete(): Boolean = missing() == null

    /** Exactly what the server expects, so no field is quietly renamed. */
    fun linesJson(): String {
        val array = JSONArray()
        entries.forEach { line ->
            array.put(
                JSONObject()
                    .put("code", line.code)
                    .put("quantity", line.quantity)
            )
        }
        return array.toString()
    }

    fun fields(): Map<String, String> = mapOf(
        "direction" to direction.wire,
        "documentDate" to dateIso,
        "voucher" to voucher.trim(),
        "location" to location.trim(),
        "engineerName" to engineer.trim(),
        "notes" to notes.trim(),
        "lines" to linesJson(),
    )
}

/** A document already sent, as the server reports it. */
data class SubmittedDocument(
    val number: String,
    val status: String,
    val statusLabel: String,
    val direction: String,
    val documentDate: String,
    val location: String,
    val engineerName: String,
    val quantity: Int,
    val itemCount: Int,
    val decisionNote: String,
)

fun parseItem(json: JSONObject): ItemInfo = ItemInfo(
    code = json.optString("code"),
    description = json.optString("description"),
    unit = json.optString("unit"),
    quantity = json.optInt("quantity", 0),
    price = json.optString("price"),
)

fun parseDocument(json: JSONObject): SubmittedDocument {
    val lines = json.optJSONArray("lines")
    return SubmittedDocument(
        number = json.optString("number"),
        status = json.optString("status"),
        statusLabel = json.optString("statusLabel"),
        direction = json.optString("direction"),
        documentDate = json.optString("documentDate"),
        location = json.optString("location"),
        engineerName = json.optString("engineerName"),
        quantity = json.optInt("quantity", 0),
        itemCount = lines?.length() ?: 0,
        decisionNote = json.optString("decisionNote"),
    )
}

fun parseDocuments(text: String): List<SubmittedDocument> {
    val array = JSONObject(text).optJSONArray("documents") ?: return emptyList()
    return (0 until array.length()).mapNotNull { index ->
        array.optJSONObject(index)?.let { parseDocument(it) }
    }
}
