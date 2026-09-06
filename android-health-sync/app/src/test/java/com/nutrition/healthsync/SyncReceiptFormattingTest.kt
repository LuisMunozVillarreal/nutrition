package com.nutrition.healthsync

import com.nutrition.healthsync.storage.SyncReceipt
import com.nutrition.healthsync.storage.SyncReceiptRecord
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
            acknowledgedAt = "2026-09-05T12:00:00Z",
            records = listOf(
                SyncReceiptRecord("2026-09-04", 9_876, "created"),
                SyncReceiptRecord("2026-09-05", 1_234, "skipped"),
            ),
            processed = 1,
            skipped = 1,
        )

        val text = formatSyncReceipt(
            receipt,
            ZoneId.of("Europe/London"),
            Locale.ENGLISH,
        )

        assertTrue(text.contains("4 Sep 2026 · 9,876 steps · Added"))
        assertTrue(text.contains("5 Sep 2026 · 1,234 steps · Not synced"))
        assertTrue(text.contains("1 day accepted · 1 day skipped"))
    }

    @Test
    fun `receipt explicitly reports an acknowledged zero-record upload`() {
        val text = formatSyncReceipt(
            SyncReceipt(
                acknowledgedAt = Instant.parse("2026-09-05T12:00:00Z").toString(),
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
                acknowledgedAt = "2026-09-05T12:00:00Z",
                records = listOf(
                    SyncReceiptRecord("2026-09-05", 1, "unchanged"),
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
