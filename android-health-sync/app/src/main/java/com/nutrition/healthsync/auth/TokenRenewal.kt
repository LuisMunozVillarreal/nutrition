package com.nutrition.healthsync.auth

import com.nutrition.healthsync.network.TokenResponse
import com.nutrition.healthsync.storage.Pairing

/** Caller holds the process-wide session mutex through refresh, upload and receipt commit. */
class TokenRenewal(
    private val load: () -> Pairing?,
    private val save: (Pairing) -> Unit,
    private val exchange: suspend (Pairing, String) -> TokenResponse,
    private val now: () -> Long,
) {
    suspend fun active(force: Boolean = false): Pairing {
        var pairing = checkNotNull(load()) { "Connect this device first" }
        if (pairing.refreshToken == null) return pairing
        if (!force && pairing.pendingRefreshToken == null && pairing.accessExpiresAt > now() + 60) return pairing
        val replacement = pairing.pendingRefreshToken ?: BrowserSignIn.secret()
        if (pairing.pendingRefreshToken == null) {
            pairing = pairing.copy(pendingRefreshToken = replacement)
            save(pairing) // Must be durable before a request that might rotate server state.
        }
        val tokens = exchange(pairing, replacement)
        require(tokens.refreshToken == replacement) { "The server returned an unexpected renewal credential" }
        return pairing.copy(
            token = tokens.accessToken, refreshToken = tokens.refreshToken,
            accessExpiresAt = now() + tokens.expiresIn, pendingRefreshToken = null,
        ).also(save)
    }
}
