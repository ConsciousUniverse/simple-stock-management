package com.cortoba.warehouse

import android.content.Context

/**
 * What survives closing the app: the token.
 *
 * The server address is NOT stored and NOT editable: it is the one this build
 * was made for. A field that could point the app at another host was a way to
 * send a warehouse password somewhere else, and a phone that remembers a typo
 * cannot be fixed by the person holding it.
 *
 * The phone number is cached for the header only. It is never written back to
 * the server — the server refuses that, and the change is a manager's decision.
 */
class Session(context: Context) {

    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString("token", null)
        set(value) = prefs.edit().putString("token", value).apply()

    val baseUrl: String = BuildConfig.DEFAULT_BASE_URL

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
        prefs.edit().remove("token").remove("phone").remove("display_name").apply()
    }

    /** Drop an address an older build saved; the field it came from is gone. */
    fun forgetStoredServer() {
        if (prefs.contains("base_url")) {
            prefs.edit().remove("base_url").apply()
        }
    }

    fun remember(profile: Profile) {
        phone = profile.phone
        displayName = profile.displayName
    }
}
