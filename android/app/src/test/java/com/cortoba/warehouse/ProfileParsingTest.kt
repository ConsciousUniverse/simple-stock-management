package com.cortoba.warehouse

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What the profile screen is allowed to show.
 *
 * The phone is displayed, never edited: `Profile` carries no setter, and the
 * screen has no field for it. The pending request is surfaced so a user who
 * asked yesterday is not left wondering whether the request was received.
 */
class ProfileParsingTest {

    @Test
    fun the_profile_the_server_sends_is_read() {
        val profile = parseProfile(
            JSONObject(
                """{"username": "shop1", "displayName": "أحمد", "role": "shop_user",
                    "phone": "+201012345678", "phoneLocked": true,
                    "pendingPhoneChange": null}"""
            )
        )

        assertEquals("shop1", profile.username)
        assertEquals("أحمد", profile.displayName)
        assertEquals("shop_user", profile.role)
        assertEquals("+201012345678", profile.phone)
        assertNull(profile.pendingPhone)
    }

    @Test
    fun a_pending_request_is_surfaced() {
        val profile = parseProfile(
            JSONObject(
                """{"username": "shop1", "phone": "+201012345678",
                    "pendingPhoneChange": {"requestedPhone": "+201099999999",
                                           "status": "pending"}}"""
            )
        )

        assertEquals("+201099999999", profile.pendingPhone)
    }

    @Test
    fun a_missing_display_name_falls_back_to_the_username() {
        val profile = parseProfile(JSONObject("""{"username": "shop1"}"""))

        assertEquals("shop1", profile.displayName)
        assertTrue(profile.phone.isEmpty())
    }
}
