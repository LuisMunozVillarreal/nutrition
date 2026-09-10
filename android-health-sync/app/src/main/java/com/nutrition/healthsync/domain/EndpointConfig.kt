package com.nutrition.healthsync.domain

import java.net.URI
import java.util.Locale

object EndpointConfig {
    fun normalize(value: String): String {
        val uri = runCatching { URI(value.trim()) }
            .getOrElse { throw IllegalArgumentException("The server URL is invalid", it) }
        require(uri.scheme?.lowercase(Locale.ROOT) == "https") {
            "The server must use HTTPS"
        }
        require(!uri.host.isNullOrBlank()) { "The URL must include a valid host" }
        require(uri.userInfo == null) { "The URL cannot include credentials" }
        require(uri.rawQuery == null && uri.rawFragment == null) {
            "The URL cannot include a query or fragment"
        }
        require(uri.rawPath.isNullOrEmpty() || uri.rawPath == "/") {
            "Enter only the server origin, without a path"
        }
        require(uri.port in -1..65535) { "The port is invalid" }

        return URI(
            "https",
            null,
            uri.host.lowercase(Locale.ROOT),
            uri.port,
            null,
            null,
            null,
        ).toASCIIString()
    }
}