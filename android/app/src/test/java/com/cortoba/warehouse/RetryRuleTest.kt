package com.cortoba.warehouse

import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What may be tried again, and what must not.
 *
 * The expensive mistake is retrying a document submission whose fate is
 * unknown: one sheet of paper would become two stock movements. The cheap
 * mistake is giving up on a sleeping server, which the operator reads as a
 * broken app.
 */
class RetryRuleTest {

    private fun ask(error: Throwable, repeatable: Boolean, attempt: Int = 0) =
        Retry.shouldRetry(repeatable, error, attempt, attempts = 6)

    @Test
    fun `a refused connection is retried even for a submission`() {
        // Nothing reached the app: Render had not started listening yet.
        assertTrue(ask(ConnectException("refused"), repeatable = false))
    }

    @Test
    fun `a booting instance is retried even for a submission`() {
        assertTrue(ask(ApiException(502, "Bad gateway"), repeatable = false))
        assertTrue(ask(ApiException(503, "Unavailable"), repeatable = false))
        assertTrue(ask(ApiException(504, "Timeout"), repeatable = false))
    }

    @Test
    fun `a timeout is not retried for a submission`() {
        // It may have been handled; repeating it could double the movement.
        assertFalse(ask(SocketTimeoutException("read timed out"), repeatable = false))
        assertFalse(ask(UnknownHostException("dns"), repeatable = false))
    }

    @Test
    fun `a timeout is retried for a read`() {
        assertTrue(ask(SocketTimeoutException("read timed out"), repeatable = true))
    }

    @Test
    fun `a refusal from the api is never retried`() {
        // 401/400/409 are answers, not transport failures.
        assertFalse(ask(ApiException(401, "Unauthorized"), repeatable = true))
        assertFalse(ask(ApiException(409, "Conflict"), repeatable = false))
    }

    @Test
    fun `the attempts are finite`() {
        assertFalse(Retry.shouldRetry(true, ConnectException("refused"), 6, 6))
        assertTrue(Retry.shouldRetry(true, ConnectException("refused"), 5, 6))
    }
}
