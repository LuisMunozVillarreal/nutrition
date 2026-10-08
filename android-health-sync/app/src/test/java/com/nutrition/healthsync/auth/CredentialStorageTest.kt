package com.nutrition.healthsync.auth

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.nutrition.healthsync.storage.SecurePairingStore
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CredentialStorageTest {
    @Test fun `manifest routes only this flavor callback and activity removes code from its intent`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val scheme = com.nutrition.healthsync.BuildConfig.APPLICATION_ID
        val callback = android.content.Intent(android.content.Intent.ACTION_VIEW,
            android.net.Uri.parse("$scheme:/oauth2redirect?code=${"c".repeat(43)}&state=${"s".repeat(43)}&issuer=https%3A%2F%2Fexample.com"))
            .addCategory(android.content.Intent.CATEGORY_BROWSABLE)
        val matches = context.packageManager.queryIntentActivities(callback, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY)
        assertTrue(matches.any { it.activityInfo.name == com.nutrition.healthsync.SettingsActivity::class.java.name })
        val otherScheme = if (scheme.endsWith(".testing")) "com.nutrition.healthsync" else "com.nutrition.healthsync.testing"
        val other = android.content.Intent(callback).setData(android.net.Uri.parse("$otherScheme:/oauth2redirect"))
        assertTrue(context.packageManager.queryIntentActivities(other, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY).isEmpty())
        val controller = org.robolectric.Robolectric.buildActivity(com.nutrition.healthsync.SettingsActivity::class.java, callback).setup()
        assertNull(controller.get().intent.data)
        controller.pause().stop().destroy()
    }

    @Test fun `disconnect refuses an unreadable envelope without clearing recovery data`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val prefs = context.getSharedPreferences("secure_health_sync_pairing", Context.MODE_PRIVATE)
        prefs.edit().putString("iv", "broken-envelope").putString("ciphertext", "retain-me").commit()
        val error = kotlinx.coroutines.runBlocking {
            runCatching { com.nutrition.healthsync.sync.SyncCoordinator(context).disconnect() }.exceptionOrNull()
        }
        assertNotNull("Cannot claim server revocation without a readable credential", error)
        assertEquals("retain-me", prefs.getString("ciphertext", null))
        prefs.edit().clear().commit()
    }

    @Test fun `unknown revoke credentials never count as confirmed server revocation`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        java.security.Security.addProvider(com.nutrition.healthsync.TestKeyProvider())
        val store = SecurePairingStore(context)
        try {
            for (status in listOf(400, 401, 200)) {
                store.save(com.nutrition.healthsync.storage.Pairing("https://example.com", "access", refreshToken = "r".repeat(43)))
                val coordinator = com.nutrition.healthsync.sync.SyncCoordinator(context)
                val api = com.nutrition.healthsync.network.HealthSyncApi(okhttp3.OkHttpClient.Builder().addInterceptor { chain ->
                    assertEquals("/api/health-sync/revoke/", chain.request().url.encodedPath)
                    okhttp3.Response.Builder().request(chain.request()).protocol(okhttp3.Protocol.HTTP_1_1)
                        .code(status).message("Rejected").body("{}".toResponseBody()).build()
                }.build())
                coordinator.javaClass.getDeclaredField("api").apply { isAccessible = true }.set(coordinator, api)
                val error = kotlinx.coroutines.runBlocking { runCatching { coordinator.disconnect() }.exceptionOrNull() }
                if (status == 200) {
                    assertNull(error)
                    assertNull(store.load())
                } else {
                    assertNotNull("Unrecognized credentials do not prove revocation", error)
                    assertNotNull(store.load())
                }
            }
        } finally {
            store.clear()
            java.security.Security.removeProvider("AccountStateTestKeys")
        }
    }

    @Test fun `a decrypt failure must never delete the only renewable credential`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val prefs = context.getSharedPreferences("secure_health_sync_pairing", Context.MODE_PRIVATE)
        prefs.edit().putString("iv", "broken-envelope").putString("ciphertext", "retain-me").commit()
        runCatching { SecurePairingStore(context).load() }
        assertEquals("retain-me", prefs.getString("ciphertext", null))
        prefs.edit().clear().commit()
    }
}
