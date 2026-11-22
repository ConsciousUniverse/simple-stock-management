package com.cortoba.warehouse

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The document rules, without a phone: what counts as the same article, what
 * must be filled before sending, and what the server is told.
 */
class DocumentDraftTest {

    private fun item(code: String, unit: String = "متر") = ItemInfo(
        code = code,
        description = "Cable $code",
        unit = unit,
        quantity = 10,
        price = "12.50",
    )

    private fun complete(): DocumentDraft = DocumentDraft(DocumentDirection.OUT).apply {
        voucher = "050340604"
        location = "مبنى B"
        engineer = "م. أحمد"
        photoPath = "/tmp/voucher.jpg"
        add(item("CBL-1"), 3)
    }

    @Test
    fun `scanning the same label twice adds to one line`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(item("CBL-1"))
        draft.add(item("CBL-1"))
        assertEquals(1, draft.itemCount)
        assertEquals(2, draft.lines.single().quantity)
    }

    @Test
    fun `two labels are two lines`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(item("CBL-1"))
        draft.add(item("CBL-2"))
        assertEquals(2, draft.itemCount)
        assertEquals(2, draft.totalQuantity)
    }

    @Test
    fun `the line keeps the unit the catalogue gave it`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(item("SKT-1", unit = "قطعة"), 4)
        assertEquals("قطعة", draft.lines.single().unit)
    }

    @Test
    fun `a quantity below one is treated as one`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(item("CBL-1"), 0)
        assertEquals(1, draft.lines.single().quantity)
        draft.setQuantity("CBL-1", -5)
        assertEquals(1, draft.lines.single().quantity)
    }

    @Test
    fun `removing a line removes it entirely`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(item("CBL-1"))
        draft.add(item("CBL-2"))
        draft.remove("CBL-1")
        assertEquals(listOf("CBL-2"), draft.lines.map { it.code })
    }

    @Test
    fun `a complete draft has nothing missing`() {
        assertNull(complete().missing())
        assertTrue(complete().isComplete())
    }

    @Test
    fun `a new draft starts dated today`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        assertEquals(todayIso(), draft.dateIso)
        assertEquals(MissingField.VOUCHER, draft.missing())
    }

    @Test
    fun `each missing thing is reported in the order it is filled`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.dateIso = ""
        assertEquals(MissingField.DATE, draft.missing())

        draft.dateIso = "2026-11-20"
        assertEquals(MissingField.VOUCHER, draft.missing())

        draft.voucher = "V-1"
        assertEquals(MissingField.LOCATION, draft.missing())

        draft.location = "موقع"
        assertEquals(MissingField.ENGINEER, draft.missing())

        draft.engineer = "م. علي"
        assertEquals(MissingField.PHOTO, draft.missing())

        draft.photoPath = "/tmp/v.jpg"
        assertEquals(MissingField.LINES, draft.missing())

        draft.add(item("CBL-1"))
        assertNull(draft.missing())
    }

    @Test
    fun `a blank photo path counts as no photo`() {
        val draft = complete()
        draft.photoPath = "   "
        assertEquals(MissingField.PHOTO, draft.missing())
    }

    @Test
    fun `the payload names the direction the server expects`() {
        assertEquals("out", DocumentDraft(DocumentDirection.OUT).fields()["direction"])
        assertEquals("in", DocumentDraft(DocumentDirection.IN).fields()["direction"])
    }

    @Test
    fun `the payload carries every field the server validates`() {
        val fields = complete().fields()
        assertEquals("050340604", fields["voucher"])
        assertEquals("مبنى B", fields["location"])
        assertEquals("م. أحمد", fields["engineerName"])
        assertEquals("2026-11-20".take(4), fields["documentDate"]!!.take(4))
        val lines = org.json.JSONArray(fields["lines"]!!)
        assertEquals(1, lines.length())
        assertEquals("CBL-1", lines.getJSONObject(0).getString("code"))
        assertEquals(3, lines.getJSONObject(0).getInt("quantity"))
    }

    @Test
    fun `the payload never sends a unit the operator could have changed`() {
        // The unit belongs to the catalogue; the phone reports what it saw and
        // the server decides. A unit in the payload would be a second opinion.
        val fields = complete().fields()
        assertFalse(fields["lines"]!!.contains("unit"))
    }

    @Test
    fun `a scanned item is read from the server's answer`() {
        val json = JSONObject(
            """{"code":"CBL-3X25","description":"Cable 3x2.5","unit":"متر","quantity":100,"price":"12.50"}"""
        )
        val parsed = parseItem(json)
        assertEquals("CBL-3X25", parsed.code)
        assertEquals("متر", parsed.unit)
        assertEquals(100, parsed.quantity)
    }

    @Test
    fun `the documents list is read with its outcome`() {
        val text = """
            {"documents":[
              {"number":"ISS-2026-0001","status":"pending","statusLabel":"Pending",
               "direction":"out","documentDate":"2026-11-20","location":"مبنى B",
               "engineerName":"م. أحمد","quantity":3,"decisionNote":"",
               "lines":[{"code":"CBL-1","quantity":3,"unit":"متر"}]},
              {"number":"ISS-2026-0002","status":"rejected","statusLabel":"Rejected",
               "direction":"out","documentDate":"2026-11-19","location":"موقع",
               "engineerName":"م. علي","quantity":1,"decisionNote":"بند غير مطابق",
               "lines":[]}
            ]}
        """.trimIndent()
        val documents = parseDocuments(text)
        assertEquals(2, documents.size)
        assertEquals("ISS-2026-0001", documents[0].number)
        assertEquals(1, documents[0].itemCount)
        assertEquals("بند غير مطابق", documents[1].decisionNote)
    }

    @Test
    fun `an empty list is not an error`() {
        assertTrue(parseDocuments("""{"documents":[]}""").isEmpty())
        assertTrue(parseDocuments("{}").isEmpty())
    }

    // ------------------------------------------------- more than the shelf

    @Test
    fun `an issue line records what the shelf held`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        val line = draft.add(ItemInfo("CBL", "Cable", "متر", 100, "0"))

        assertEquals(100, line.available)
        assertFalse(line.exceedsShelf)
    }

    @Test
    fun `an addition is never capped by the shelf`() {
        val draft = DocumentDraft(DocumentDirection.IN)
        val line = draft.add(ItemInfo("CBL", "Cable", "متر", 0, "0"))

        assertNull(line.available)
        assertFalse(line.exceedsShelf)
        draft.setQuantity("CBL", 5000)
        assertNull(draft.overIssued())
    }

    @Test
    fun `asking for more than the shelf is flagged`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(ItemInfo("CBL", "Cable", "متر", 100, "0"))
        draft.setQuantity("CBL", 101)

        assertTrue(draft.lines.first().exceedsShelf)
        assertEquals("CBL", draft.overIssued()?.code)
    }

    @Test
    fun `exactly the shelf is allowed`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(ItemInfo("CBL", "Cable", "متر", 100, "0"))
        draft.setQuantity("CBL", 100)

        assertNull(draft.overIssued())
    }

    @Test
    fun `scanning past the shelf flags the line the scan landed on`() {
        val draft = DocumentDraft(DocumentDirection.OUT)
        draft.add(ItemInfo("CBL", "Cable", "متر", 1, "0"))
        draft.add(ItemInfo("CBL", "Cable", "متر", 1, "0"))

        assertEquals(2, draft.lines.first().quantity)
        assertTrue(draft.lines.first().exceedsShelf)
    }
}
