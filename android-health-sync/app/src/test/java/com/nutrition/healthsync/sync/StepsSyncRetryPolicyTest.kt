package com.nutrition.healthsync.sync

import com.nutrition.healthsync.network.ApiException
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StepsSyncRetryPolicyTest {
    @Test
    fun `transport and temporary HTTP failures are retried`() {
        assertTrue(ApiException("transport", retryable = true).isRetryableForBackgroundSync())
        assertTrue(ApiException("timeout", statusCode = 408).isRetryableForBackgroundSync())
        assertTrue(ApiException("limited", statusCode = 429).isRetryableForBackgroundSync())
        assertTrue(ApiException("server", statusCode = 503).isRetryableForBackgroundSync())
    }

    @Test
    fun `malformed responses and permanent HTTP failures are not retried`() {
        assertFalse(ApiException("malformed").isRetryableForBackgroundSync())
        assertFalse(ApiException("unauthorized", statusCode = 401).isRetryableForBackgroundSync())
        assertFalse(ApiException("invalid", statusCode = 422).isRetryableForBackgroundSync())
    }
}