package com.nutrition.healthsync.sync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class SyncReceiptUpdatesTest {
    @Test
    fun `receipt updates emits again when the encrypted envelope changes`() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val preferences = context.getSharedPreferences(
            "secure_health_sync_pairing",
            Context.MODE_PRIVATE,
        )
        preferences.edit().clear().commit()
        val firstEmission = CompletableDeferred<Unit>()
        val values = mutableListOf<Any?>()

        val collection = async {
            withTimeout(2_000) {
                SyncCoordinator(context).receiptUpdates()
                    .onEach { if (values.isEmpty()) firstEmission.complete(Unit) }
                    .take(2)
                    .toList(values)
            }
        }
        firstEmission.await()
        preferences.edit().putString("iv", "changed-envelope").commit()
        collection.await()

        assertEquals(listOf(null, null), values)
    }
}
