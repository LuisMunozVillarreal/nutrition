package com.nutrition.healthsync.auth

import com.nutrition.healthsync.domain.EndpointConfig
import java.net.URI
import java.net.URLDecoder
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import kotlinx.serialization.Serializable
import okhttp3.HttpUrl.Companion.toHttpUrl

@Serializable
class PendingSignIn(
    val baseUrl: String,
    val verifier: String,
    val state: String,
    val redirectUri: String,
    val deviceName: String,
    val createdAt: Long,
)

object BrowserSignIn {
    fun secret(): String = Base64.getUrlEncoder().withoutPadding()
        .encodeToString(ByteArray(32).also { SecureRandom().nextBytes(it) })

    fun challenge(verifier: String): String = Base64.getUrlEncoder().withoutPadding()
        .encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))

    fun start(origin: String, name: String, applicationId: String, now: Long): PendingSignIn {
        require(name.trim().length in 1..120) { "Enter a device name of up to 120 characters" }
        require(applicationId in setOf("com.nutrition.healthsync", "com.nutrition.healthsync.testing"))
        return PendingSignIn(
            EndpointConfig.normalize(origin).toHttpUrl().toString().trimEnd('/'),
            secret(), secret(), "$applicationId:/oauth2redirect", name.trim(), now,
        )
    }

    fun browserUrl(pending: PendingSignIn): String = pending.baseUrl.toHttpUrl().newBuilder()
        .addPathSegments("health-sync/authorize")
        .addQueryParameter("issuer", pending.baseUrl)
        .addQueryParameter("redirect_uri", pending.redirectUri)
        .addQueryParameter("state", pending.state)
        .addQueryParameter("code_challenge", challenge(pending.verifier))
        .addQueryParameter("code_challenge_method", "S256")
        .addQueryParameter("device_name", pending.deviceName)
        .build().toString()

    fun complete(pending: PendingSignIn, callback: String, now: Long): String? {
        val uri = URI(callback)
        require("${uri.scheme}:${uri.rawPath}" == pending.redirectUri && uri.rawAuthority == null && uri.rawFragment == null) {
            "The sign-in response is not for this app"
        }
        require(now - pending.createdAt in 0..600) { "Sign-in expired. Start again." }
        val query = uri.rawQuery.orEmpty().split('&').map {
            val parts = it.split('=', limit = 2)
            require(parts.size == 2) { "Invalid sign-in response" }
            URLDecoder.decode(parts[0], "UTF-8") to URLDecoder.decode(parts[1], "UTF-8")
        }
        require(query.map { it.first }.distinct().size == query.size) { "Invalid sign-in response" }
        val params = query.toMap()
        require(params["state"] == pending.state && params["issuer"] == pending.baseUrl) {
            "The sign-in response does not match the requested server"
        }
        if (params["error"] == "access_denied" && params["code"] == null) return null
        val code = params["code"].orEmpty()
        require(params["error"] == null && code.matches(Regex("[A-Za-z0-9_-]{43}"))) { "Invalid sign-in response" }
        return code
    }
}
