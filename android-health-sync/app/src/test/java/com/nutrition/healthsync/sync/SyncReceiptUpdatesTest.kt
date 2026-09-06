package com.nutrition.healthsync.sync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class SyncReceiptUpdatesTest {
    @Test
    fun `receipt updates emits the current empty state`() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("secure_health_sync_pairing", Context.MODE_PRIVATE)
            .edit()
            .clear()
            .commit()

        val receipt = withTimeout(2_000) {
            SyncCoordinator(context).receiptUpdates().first()
        }

        assertNull(receipt)
    }
}
