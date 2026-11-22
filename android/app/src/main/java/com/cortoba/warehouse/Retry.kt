package com.cortoba.warehouse

import java.net.ConnectException
import java.net.SocketTimeoutException

/**
 * Whether a failed call should be tried again.
 *
 * The reason this is not "retry everything": a document submission is not
 * idempotent, so retrying one whose fate is unknown would put two stock
 * movements on the books for one sheet of paper. The rule separates the
 * failures that prove the request never arrived from the ones that leave it
 * unknown.
 */
object Retry {

    /** The proxy's way of saying the instance is not serving yet. */
    private fun isWaking(status: Int): Boolean = status == 502 || status == 503 || status == 504

    /**
     * @param repeatable the call may be repeated without changing the outcome
     *   (a read, or a sign-in that only opens a session).
     */
    fun shouldRetry(
        repeatable: Boolean,
        error: Throwable,
        attempt: Int,
        attempts: Int,
    ): Boolean {
        if (attempt >= attempts) return false
        return when (error) {
            // The app was not listening: nothing reached it, whatever the verb.
            is ConnectException -> true
            // The instance is booting; the proxy answered instead of the app.
            is ApiException -> isWaking(error.status)
            // A timeout cannot tell "handled" from "not handled" — only safe
            // when repeating the call cannot change the outcome.
            is SocketTimeoutException -> repeatable
            is java.io.IOException -> repeatable
            else -> false
        }
    }
}
