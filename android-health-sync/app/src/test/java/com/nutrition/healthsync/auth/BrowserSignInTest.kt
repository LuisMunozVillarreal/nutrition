package com.nutrition.healthsync.auth

import java.net.URI
import org.junit.Assert.*
import org.junit.Test

class BrowserSignInTest {
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
