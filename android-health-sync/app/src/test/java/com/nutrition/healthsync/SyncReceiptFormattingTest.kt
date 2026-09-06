package com.nutrition.healthsync

import com.nutrition.healthsync.network.StepUploadRecord
import com.nutrition.healthsync.storage.SyncReceipt
import java.time.Instant
import java.time.ZoneId
import java.util.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SyncReceiptFormattingTest {
    @Test
    fun `connected device state is explicit`() {
        assertEquals("DEVICE CONNECTED", formatConnectionState(true))
        assertEquals("DEVICE NOT CONNECTED", formatConnectionState(false))
    }

    @Test
    fun `receipt lists the exact daily totals acknowledged by Nutrition`() {
        val receipt = SyncReceipt(
            syncedAt = "2026-09-05T12:00:00Z",
            records = listOf(
                StepUploadRecord("2026-09-04", 9_876, "2026-09-05T12:00:00Z"),
                StepUploadRecord("2026-09-05", 1_234, "2026-09-05T12:00:00Z"),
            ),
            processed = 2,
            skipped = 0,
        )

        val text = formatSyncReceipt(
            receipt,
            ZoneId.of("Europe/London"),
            Locale.ENGLISH,
        )

        assertTrue(text.contains("4 Sep 2026 · 9,876 steps"))
        assertTrue(text.contains("5 Sep 2026 · 1,234 steps"))
        assertTrue(text.contains("2 days accepted"))
    }

    @Test
    fun `receipt explicitly reports an acknowledged zero-record upload`() {
        val text = formatSyncReceipt(
            SyncReceipt(
                syncedAt = Instant.parse("2026-09-05T12:00:00Z").toString(),
                records = emptyList(),
                processed = 0,
                skipped = 0,
            ),
            ZoneId.of("UTC"),
            Locale.ENGLISH,
        )

        assertTrue(text.contains("No daily step totals were sent"))
    }

    @Test
    fun `receipt uses singular day for one accepted total`() {
        val text = formatSyncReceipt(
            SyncReceipt(
                syncedAt = "2026-09-05T12:00:00Z",
                records = listOf(
                    StepUploadRecord("2026-09-05", 1, "2026-09-05T12:00:00Z"),
                ),
                processed = 1,
                skipped = 0,
            ),
            ZoneId.of("UTC"),
            Locale.ENGLISH,
        )

        assertTrue(text.startsWith("1 day accepted"))
    }
}
