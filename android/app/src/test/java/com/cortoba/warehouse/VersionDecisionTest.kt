package com.cortoba.warehouse

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The update decision is made by the app, not taken from the server's wording.
 *
 * A response that says "update" for a build the phone already has must not open
 * a dialog; one that hides a higher build must not hide it either. These are
 * the cases that decide whether a phone in a drawer ever gets the new build.
 */
class VersionDecisionTest {

    private fun payload(
        code: Int,
        url: String = "https://example.com/app.apk",
        name: String = "1.0.$code",
        mandatory: Boolean = false,
        sha: String = "",
        size: Long = 0,
    ) = """
        {"updateAvailable": true,
         "latest": {"versionCode": $code, "versionName": "$name",
                    "downloadUrl": "$url", "notes": "faster",
                    "mandatory": $mandatory, "sha256": "$sha", "sizeBytes": $size}}
    """.trimIndent()

    @Test
    fun a_higher_build_is_an_update() {
        val info = parseVersionResponse(payload(7))!!

        assertTrue(info.isNewerThan(6))
    }

    @Test
    fun the_same_build_is_not_an_update_even_when_the_server_says_so() {
        val info = parseVersionResponse(payload(6))!!

        assertFalse(info.isNewerThan(6))
    }

    @Test
    fun a_lower_build_is_never_offered_so_nobody_is_downgraded() {
        val info = parseVersionResponse(payload(5))!!

        assertFalse(info.isNewerThan(6))
    }

    @Test
    fun nothing_published_means_no_update() {
        assertNull(parseVersionResponse("""{"updateAvailable": false, "latest": null}"""))
    }

    @Test
    fun a_release_without_a_build_number_is_not_an_update() {
        // Without a number there is nothing to compare, so offering it would
        // open a dialog on every launch forever.
        assertNull(parseVersionResponse("""{"latest": {"versionName": "1.0.0"}}"""))
    }

    @Test
    fun a_release_without_an_address_is_not_installable() {
        assertNull(parseVersionResponse(payload(9, url = "")))
    }

    @Test
    fun the_details_the_installer_needs_are_read() {
        val info = parseVersionResponse(
            payload(12, name = "1.2.0", mandatory = true, sha = "AB".repeat(32), size = 42)
        )!!

        assertEquals("1.2.0", info.versionName)
        assertEquals(12, info.versionCode)
        assertEquals("faster", info.notes)
        assertTrue(info.mandatory)
        assertEquals("ab".repeat(32), info.sha256)
        assertEquals(42L, info.sizeBytes)
    }

    @Test
    fun a_mandatory_build_is_reported_as_mandatory() {
        val optional = parseVersionResponse(payload(4, mandatory = false))!!
        val required = parseVersionResponse(payload(4, mandatory = true))!!

        assertFalse(optional.mandatory)
        assertTrue(required.mandatory)
    }

    @Test
    fun a_missing_version_name_falls_back_to_the_build_number() {
        val info = parseVersionResponse(
            """{"latest": {"versionCode": 8, "downloadUrl": "https://e/x.apk"}}"""
        )!!

        assertEquals("8", info.versionName)
    }
}
