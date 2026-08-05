package com.nutrition.healthsync.network

import kotlinx.serialization.encodeToString
import org.junit.Assert.assertEquals
import org.junit.Test

class HealthSyncJsonTest {
    @Test
    fun `serializa pairing con los nombres exactos del contrato`() {
        val json = HealthSyncJson.codec.encodeToString(
            PairRequest(code = "123456789012", deviceName = "Galaxy de pruebas"),
        )

        assertEquals(
            "{\"code\":\"123456789012\",\"device_name\":\"Galaxy de pruebas\"}",
            json,
        )
    }

    @Test
    fun `serializa pasos diarios con fecha observada ISO 8601`() {
        val json = HealthSyncJson.codec.encodeToString(
            StepsUploadRequest(
                records = listOf(
                    StepUploadRecord(
                        date = "2026-07-30",
                        steps = 8_765,
                        observedAt = "2026-07-31T08:15:30Z",
                    ),
                ),
            ),
        )

        assertEquals(
            "{\"records\":[{\"date\":\"2026-07-30\",\"steps\":8765,\"observed_at\":\"2026-07-31T08:15:30Z\"}]}",
            json,
        )
    }

    @Test
    fun `deserializa token aunque backend agregue metadatos`() {
        val response = HealthSyncJson.codec.decodeFromString<PairResponse>(
            """{"token":"scoped-token","device_id":"ignored"}""",
        )

        assertEquals("scoped-token", response.token)
    }

    @Test
    fun `deserializa resumen real de sincronizacion`() {
        val response = HealthSyncJson.codec.decodeFromString<StepsUploadResponse>(
            """{"summary":{"created":2,"updated":1,"unchanged":3,"skipped":4},"records":[]}""",
        )

        assertEquals(6, response.summary.processed)
        assertEquals(4, response.summary.skipped)
    }
}