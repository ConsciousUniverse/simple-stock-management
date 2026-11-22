package com.cortoba.warehouse

import android.content.Context

/**
 * What survives closing the app: the token and the server it belongs to.
 *
 * The phone number is cached for the header only. It is never written back to
 * the server — the server refuses that, and the change is a manager's decision.
 */
class Session(context: Context) {

    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString("token", null)
        set(value) = prefs.edit().putString("token", value).apply()

    var baseUrl: String
        get() = prefs.getString("base_url", null) ?: BuildConfig.DEFAULT_BASE_URL
        set(value) {
            val normalised = if (value.endsWith("/")) value else "$value/"
            prefs.edit().putString("base_url", normalised).apply()
        }

    var phone: String
        get() = prefs.getString("phone", "").orEmpty()
        set(value) = prefs.edit().putString("phone", value).apply()

    var displayName: String
        get() = prefs.getString("display_name", "").orEmpty()
        set(value) = prefs.edit().putString("display_name", value).apply()

    val isSignedIn: Boolean
        get() = !token.isNullOrEmpty()

    fun api(): Api = Api(baseUrl)

    fun clear() {
        // The server address is kept: a user signing out has not moved site.
        prefs.edit().remove("token").remove("phone").remove("display_name").apply()
    }

    fun remember(profile: Profile) {
        phone = profile.phone
        displayName = profile.displayName
    }
}
