package com.nutrition.healthsync.auth

import com.nutrition.healthsync.network.ApiException
import com.nutrition.healthsync.network.TokenResponse
import com.nutrition.healthsync.storage.Pairing
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class TokenRenewalTest {
    @Test fun `lost response preserves the exact durable replacement for a later retry`() = runBlocking {
        var saved = Pairing("https://example.com", "old-access", refreshToken = "r".repeat(43), accessExpiresAt = 0)
        var calls = 0
        val renew = TokenRenewal(
            load = { saved }, save = { saved = it }, now = { 1000 },
            exchange = { pairing, replacement ->
                assertEquals(replacement, saved.pendingRefreshToken)
                assertEquals(pairing.refreshToken, saved.refreshToken)
                calls++
                if (calls == 1) throw ApiException("Offline", retryable = true)
                TokenResponse("new-access", replacement, 900, "Bearer", "health-sync:steps")
            },
        )
        try { renew.active(); fail("Expected transport failure") } catch (_: ApiException) { }
        val pending = saved.pendingRefreshToken
        assertNotNull(pending)
        assertEquals("r".repeat(43), saved.refreshToken)
        val active = renew.active()
        assertEquals(pending, active.refreshToken)
        assertNull(active.pendingRefreshToken)
        assertEquals("new-access", active.token)
        assertEquals(1900, active.accessExpiresAt)
        renew.active()
        assertEquals(2, calls)
    }

    @Test fun `legacy pairing does not call refresh and invalid grants preserve local receipts`() = runBlocking {
        var saved = Pairing("https://example.com", "legacy")
        val renew = TokenRenewal({ saved }, { saved = it }, { _, _ -> throw ApiException("Rejected", 400) }, { 1000 })
        assertEquals(saved, renew.active())
        saved = saved.copy(refreshToken = "r".repeat(43))
        try { renew.active(); fail("Expected rejection") } catch (_: ApiException) { }
        assertEquals("r".repeat(43), saved.refreshToken)
    }
}
