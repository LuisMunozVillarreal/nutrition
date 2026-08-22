package com.nutrition.healthsync.domain

import java.net.URI
import java.util.Locale

object EndpointConfig {
    fun normalize(value: String): String {
        val uri = runCatching { URI(value.trim()) }
            .getOrElse { throw IllegalArgumentException("La URL del servidor no es válida", it) }
        require(uri.scheme?.lowercase(Locale.ROOT) == "https") {
            "El servidor debe usar HTTPS"
        }
        require(!uri.host.isNullOrBlank()) { "La URL debe incluir un host válido" }
        require(uri.userInfo == null) { "La URL no puede incluir credenciales" }
        require(uri.rawQuery == null && uri.rawFragment == null) {
            "La URL no puede incluir consulta ni fragmento"
        }
        require(uri.rawPath.isNullOrEmpty() || uri.rawPath == "/") {
            "Introduce solo el origen, sin rutas"
        }
        require(uri.port in -1..65535) { "El puerto no es válido" }

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