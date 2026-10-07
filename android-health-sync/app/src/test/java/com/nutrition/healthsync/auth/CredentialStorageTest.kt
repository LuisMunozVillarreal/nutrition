package com.nutrition.healthsync.auth

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.nutrition.healthsync.storage.SecurePairingStore
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CredentialStorageTest {
    @Test fun `a decrypt failure must never delete the only renewable credential`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val prefs = context.getSharedPreferences("secure_health_sync_pairing", Context.MODE_PRIVATE)
        prefs.edit().putString("iv", "broken-envelope").putString("ciphertext", "retain-me").commit()
        runCatching { SecurePairingStore(context).load() }
        assertEquals("retain-me", prefs.getString("ciphertext", null))
        prefs.edit().clear().commit()
    }
}
