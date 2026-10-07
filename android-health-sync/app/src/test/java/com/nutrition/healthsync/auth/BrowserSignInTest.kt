package com.nutrition.healthsync.auth

import java.net.URI
import org.junit.Assert.*
import org.junit.Test

class BrowserSignInTest {
    @Test fun `serialized pending sign-in survives process recreation and cancellation is bound to it`() {
        val original = BrowserSignIn.start("https://example.com", "Phone", "com.nutrition.healthsync.testing", 100)
        val codec = com.nutrition.healthsync.network.HealthSyncJson.codec
        val restored = codec.decodeFromString(PendingSignIn.serializer(), codec.encodeToString(PendingSignIn.serializer(), original))
        val callback = "${restored.redirectUri}?error=access_denied&state=${restored.state}&issuer=https%3A%2F%2Fexample.com"
        assertEquals(original.verifier, restored.verifier)
        assertNull(BrowserSignIn.complete(restored, callback, 101))
        for (invalid in listOf(
            callback.replace("oauth2redirect", "other"),
            callback.replace(":/oauth2redirect", "://evil.example.com/oauth2redirect"),
            callback.replace(restored.state, "x".repeat(43)),
            "$callback&code=${"c".repeat(43)}",
        )) assertThrows(IllegalArgumentException::class.java) { BrowserSignIn.complete(restored, invalid, 101) }
        assertThrows(IllegalArgumentException::class.java) { BrowserSignIn.complete(restored, callback, 99) }
    }

    @Test fun `PKCE uses the RFC S256 test vector and never puts verifier in browser URL`() {
        val verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        assertEquals("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", BrowserSignIn.challenge(verifier))
        val pending = BrowserSignIn.start("https://example.com", "Phone", "com.nutrition.healthsync", 100)
        val url = BrowserSignIn.browserUrl(pending)
        assertEquals("https", URI(url).scheme)
        assertTrue(url.contains("code_challenge_method=S256"))
        assertFalse(url.contains(pending.verifier))
        assertEquals(43, pending.state.length)
        val callback = "${pending.redirectUri}?code=${"c".repeat(43)}&state=${pending.state}&issuer=https%3A%2F%2Fexample.com"
        assertEquals("c".repeat(43), BrowserSignIn.complete(pending, callback, 101))
        for (invalid in listOf(
            callback.replace(pending.state, "x".repeat(43)),
            callback.replace("example.com", "other.example.com"),
            callback.replace("com.nutrition.healthsync:", "com.nutrition.healthsync.testing:"),
            "$callback&code=${"d".repeat(43)}",
            "$callback#fragment",
        )) assertThrows(IllegalArgumentException::class.java) { BrowserSignIn.complete(pending, invalid, 101) }
        assertThrows(IllegalArgumentException::class.java) { BrowserSignIn.complete(pending, callback, 1000) }
    }
}
