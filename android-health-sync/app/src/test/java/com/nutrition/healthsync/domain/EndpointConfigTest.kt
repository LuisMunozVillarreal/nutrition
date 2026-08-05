package com.nutrition.healthsync.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class EndpointConfigTest {
    @Test
    fun `normaliza una URL HTTPS y elimina la barra final`() {
        assertEquals("https://example.com", EndpointConfig.normalize(" https://example.com/ "))
    }

    @Test
    fun `rechaza HTTP incluso si la URL es sintacticamente valida`() {
        assertThrows(IllegalArgumentException::class.java) {
            EndpointConfig.normalize("http://example.com")
        }
    }

    @Test
    fun `rechaza rutas consultas fragmentos y credenciales`() {
        listOf(
            "https://example.com/api",
            "https://example.com?x=1",
            "https://example.com#part",
            "https://user@example.com",
        ).forEach { value ->
            assertThrows(value, IllegalArgumentException::class.java) {
                EndpointConfig.normalize(value)
            }
        }
    }
}
