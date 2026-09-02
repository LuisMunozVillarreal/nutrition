package com.nutrition.healthsync.health

import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class NonOverlappingIntervalsTest {
    private data class Interval(
        val name: String,
        val start: Instant,
        val end: Instant,
        val eligible: Boolean = true,
    )

    @Test
    fun `keeps a deterministic non-overlapping set and permits adjacent sessions`() {
        val base = Instant.parse("2026-09-02T08:00:00Z")
        val nested = Interval("nested", base.plusSeconds(600), base.plusSeconds(1200))
        val first = Interval("first", base, base.plusSeconds(1800))
        val adjacent = Interval("adjacent", base.plusSeconds(1800), base.plusSeconds(2400))

        val accepted = keepNonOverlapping(
            listOf(nested, adjacent, first),
            startOf = Interval::start,
            endOf = Interval::end,
            isEligible = Interval::eligible,
        )

        assertEquals(listOf("first", "adjacent"), accepted.map(Interval::name))
    }

    @Test
    fun `ineligible interval cannot suppress an overlapping valid session`() {
        val base = Instant.parse("2026-09-02T08:00:00Z")
        val invalid = Interval("invalid", base, base.plusSeconds(3600), eligible = false)
        val valid = Interval("valid", base.plusSeconds(60), base.plusSeconds(1800))

        val accepted = keepNonOverlapping(
            listOf(invalid, valid),
            startOf = Interval::start,
            endOf = Interval::end,
            isEligible = Interval::eligible,
        )

        assertEquals(listOf("valid"), accepted.map(Interval::name))
    }
}