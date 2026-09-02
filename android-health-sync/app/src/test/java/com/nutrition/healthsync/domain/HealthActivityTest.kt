package com.nutrition.healthsync.domain

import java.time.Instant
import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class HealthActivityTest {
    private val modifiedAt = Instant.parse("2026-09-02T08:59:00Z")
    private val start = Instant.parse("2026-09-02T09:00:00Z")
    private val end = Instant.parse("2026-09-02T09:45:30Z")

    @Test
    fun `convierte una actividad Garmin al contrato de subida`() {
        val record = HealthActivity(
            sourceRecordId = "garmin-activity-42",
            sourceModifiedAt = modifiedAt,
            startTime = start,
            endTime = end,
            type = "run",
            activeKcals = 420,
            distanceKm = 7.25,
        ).toUploadRecord()

        assertEquals("garmin-activity-42", record.sourceRecordId)
        assertEquals("2026-09-02T08:59:00Z", record.sourceModifiedAt)
        assertEquals("2026-09-02T09:00Z", record.startTime)
        assertEquals("2026-09-02T09:45:30Z", record.endTime)
        assertEquals("run", record.type)
        assertEquals(420, record.activeKcals)
        assertEquals(7.25, record.distanceKm!!, 0.0)
    }

    @Test
    fun `preserva distancia ausente sin inventarla`() {
        val record = HealthActivity(
            sourceRecordId = "garmin-activity-43",
            sourceModifiedAt = modifiedAt,
            startTime = start,
            endTime = end,
            type = "gym",
            activeKcals = 200,
            distanceKm = null,
        ).toUploadRecord()

        assertNull(record.distanceKm)
    }

    @Test
    fun `preserva el desfase local de la sesion`() {
        val record = HealthActivity(
            sourceRecordId = "garmin-travel",
            sourceModifiedAt = modifiedAt,
            startTime = Instant.parse("2026-09-01T23:30:00Z"),
            endTime = Instant.parse("2026-09-02T00:30:00Z"),
            type = "walk",
            activeKcals = 100,
            distanceKm = 4.0,
            startZoneOffset = ZoneOffset.ofHours(2),
            endZoneOffset = ZoneOffset.ofHours(2),
        ).toUploadRecord()

        assertEquals("2026-09-02T01:30+02:00", record.startTime)
        assertEquals("2026-09-02T02:30+02:00", record.endTime)
    }

    @Test
    fun `rechaza intervalos y valores imposibles`() {
        assertThrows(IllegalArgumentException::class.java) {
            HealthActivity("id", modifiedAt, end, start, "run", 1, 1.0)
        }
        assertThrows(IllegalArgumentException::class.java) {
            HealthActivity("id", modifiedAt, start, end, "run", -1, 1.0)
        }
        assertThrows(IllegalArgumentException::class.java) {
            HealthActivity("id", modifiedAt, start, end, "run", 1, -0.1)
        }
        assertThrows(IllegalArgumentException::class.java) {
            HealthActivity("id", modifiedAt, start, end, "swim", 1, 1.0)
        }
    }
}
