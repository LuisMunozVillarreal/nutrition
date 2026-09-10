package com.nutrition.healthsync.network

import com.nutrition.healthsync.storage.Pairing
import com.nutrition.healthsync.storage.SyncReceipt
import com.nutrition.healthsync.storage.SyncReceiptRecord
import kotlinx.serialization.encodeToString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HealthSyncJsonTest {
    @Test
    fun `existing encrypted pairing remains readable before receipts existed`() {
        val pairing = HealthSyncJson.codec.decodeFromString<Pairing>(
            """{"baseUrl":"https://example.com","token":"scoped-token"}""",
        )

        assertEquals("https://example.com", pairing.baseUrl)
        assertEquals("scoped-token", pairing.token)
        assertNull(pairing.lastReceipt)
    }

    @Test
    fun `receipt migration keeps pairing from the first version 1_4 build`() {
        val pairing = HealthSyncJson.codec.decodeFromString<Pairing>(
            """{"baseUrl":"https://example.com","token":"scoped-token","lastReceipt":{"syncedAt":"2026-09-05T12:00:00Z","records":[{"date":"2026-09-05","steps":1234,"observed_at":"2026-09-05T11:59:00Z"}],"processed":1,"skipped":0}}""",
        )

        assertEquals("2026-09-05T12:00:00Z", pairing.lastReceipt?.acknowledgedAt)
        assertEquals("unknown", pairing.lastReceipt?.records?.single()?.status)
    }

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
            """{"summary":{"created":1,"updated":0,"unchanged":0,"skipped":1},"records":[{"date":"2026-09-04","status":"created"},{"date":"2026-09-05","status":"skipped"}]}""",
        )

        assertEquals(1, response.summary.processed)
        assertEquals(1, response.summary.skipped)
        assertEquals("2026-09-04", response.records[0].date)
        assertEquals("created", response.records[0].status)
        assertEquals("skipped", response.records[1].status)
    }

    @Test
    fun `receipt migration tolerates records without a skip reason`() {
        val pairing = HealthSyncJson.codec.decodeFromString<Pairing>(
            """{"baseUrl":"https://example.com","token":"scoped-token","lastReceipt":{"syncedAt":"2026-09-05T12:00:00Z","records":[{"date":"2026-09-05","steps":1234,"status":"skipped"}],"processed":0,"skipped":1}}""",
        )

        val record = pairing.lastReceipt?.records?.single()
        assertEquals("skipped", record?.status)
        assertNull(record?.reason)
    }

    @Test
    fun `receipt round-trips the skip reason for each record`() {
        val pairing = Pairing(
            baseUrl = "https://example.com",
            token = "scoped-token",
            lastReceipt = SyncReceipt(
                acknowledgedAt = "2026-09-05T12:00:00Z",
                records = listOf(
                    SyncReceiptRecord("2026-09-05", 1_234, "skipped", "missing_plan_day"),
                ),
                processed = 0,
                skipped = 1,
            ),
        )

        val json = HealthSyncJson.codec.encodeToString(Pairing.serializer(), pairing)
        val decoded = HealthSyncJson.codec.decodeFromString<Pairing>(json)

        assertEquals("missing_plan_day", decoded.lastReceipt?.records?.single()?.reason)
    }

    @Test
    fun `deserializa skipped record con motivo de maquina`() {
        val response = HealthSyncJson.codec.decodeFromString<StepsUploadResponse>(
            """{"summary":{"created":0,"updated":0,"unchanged":0,"skipped":1},"records":[{"date":"2026-09-05","status":"skipped","reason":"missing_plan_day"}]}""",
        )

        assertEquals("missing_plan_day", response.records[0].reason)
    }

    @Test
    fun `deserializa skipped record sin motivo como nulo`() {
        val response = HealthSyncJson.codec.decodeFromString<StepsUploadResponse>(
            """{"summary":{"created":0,"updated":0,"unchanged":0,"skipped":1},"records":[{"date":"2026-09-05","status":"skipped"}]}""",
        )

        assertNull(response.records[0].reason)
    }
}