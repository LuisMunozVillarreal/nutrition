package com.nutrition.healthsync.domain

import java.time.Instant
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class DailyStepsTest {
    @Test
    fun `convierte agregacion diaria al contrato de subida`() {
        val record = DailySteps(
            date = LocalDate.of(2026, 7, 30),
            steps = 12_345,
        ).toUploadRecord(Instant.parse("2026-07-31T08:15:30Z"))

        assertEquals("2026-07-30", record.date)
        assertEquals(12_345, record.steps)
        assertEquals("2026-07-31T08:15:30Z", record.observedAt)
    }

    @Test
    fun `rechaza conteos negativos imposibles`() {
        assertThrows(IllegalArgumentException::class.java) {
            DailySteps(LocalDate.of(2026, 7, 30), -1)
        }
    }
}