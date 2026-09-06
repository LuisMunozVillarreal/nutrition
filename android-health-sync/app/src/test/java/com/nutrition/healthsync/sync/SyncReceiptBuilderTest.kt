package com.nutrition.healthsync.sync

import com.nutrition.healthsync.network.StepUploadRecord
import com.nutrition.healthsync.network.StepUploadResult
import com.nutrition.healthsync.network.StepsUploadResponse
import com.nutrition.healthsync.network.StepsUploadSummary
import com.nutrition.healthsync.storage.SyncReceiptRecord
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Test

class SyncReceiptBuilderTest {
    @Test
    fun `receipt maps each acknowledged status to the sent daily total`() {
        val sent = listOf(
            StepUploadRecord("2026-09-04", 9_876, "2026-09-05T12:00:00Z"),
            StepUploadRecord("2026-09-05", 1_234, "2026-09-05T12:00:00Z"),
        )
        val response = StepsUploadResponse(
            summary = StepsUploadSummary(created = 1, updated = 0, unchanged = 0, skipped = 1),
            records = listOf(
                StepUploadResult("2026-09-04", "created"),
                StepUploadResult("2026-09-05", "skipped"),
            ),
        )

        val receipt = buildSyncReceipt(
            sent = sent,
            response = response,
            acknowledgedAt = Instant.parse("2026-09-05T12:00:03Z"),
        )

        assertEquals("2026-09-05T12:00:03Z", receipt.acknowledgedAt)
        assertEquals(
            listOf(
                SyncReceiptRecord("2026-09-04", 9_876, "created"),
                SyncReceiptRecord("2026-09-05", 1_234, "skipped"),
            ),
            receipt.records,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun `receipt rejects acknowledgments for dates that were not sent`() {
        buildSyncReceipt(
            sent = listOf(
                StepUploadRecord("2026-09-04", 9_876, "2026-09-05T12:00:00Z"),
            ),
            response = StepsUploadResponse(
                summary = StepsUploadSummary(
                    created = 1,
                    updated = 0,
                    unchanged = 0,
                    skipped = 0,
                ),
                records = listOf(StepUploadResult("2026-09-03", "created")),
            ),
            acknowledgedAt = Instant.parse("2026-09-05T12:00:03Z"),
        )
    }
}
