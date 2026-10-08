package com.nutrition.healthsync.auth

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import com.nutrition.healthsync.TestKeyProvider
import com.nutrition.healthsync.network.TokenResponse
import com.nutrition.healthsync.storage.Pairing
import com.nutrition.healthsync.storage.SecurePairingStore
import java.security.Security
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class DurableCredentialStorageTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Before fun setup() { Security.addProvider(TestKeyProvider()) }
    @After fun cleanup() { Security.removeProvider("AccountStateTestKeys") }

    private fun store(prefs: SharedPreferences) = SecurePairingStore(object : ContextWrapper(context) {
        override fun getSharedPreferences(name: String, mode: Int) = prefs
    })

    private fun preferences(disk: Map<String, *> = emptyMap<String, String>()): FaultPreferences {
        val prefs = context.getSharedPreferences(UUID.randomUUID().toString(), Context.MODE_PRIVATE)
        val editor = prefs.edit()
        disk.forEach { (key, value) -> editor.putString(key, value as String) }
        editor.commit()
        return FaultPreferences(prefs)
    }

    @Test fun `failed pending write is not trusted by the next renewal or recreation`() = runBlocking {
        val prefs = preferences()
        store(prefs).save(Pairing("https://example.com", "old-access", refreshToken = "r".repeat(43)))
        val durable = prefs.disk
        var requests = 0
        fun renew(current: SecurePairingStore) = TokenRenewal(current::load, current::save, { _, token ->
            requests++
            TokenResponse("new-access", token, 900, "Bearer", "health-sync:steps")
        }, { 1000 })
        prefs.fail = true
        assertTrue(runCatching { renew(store(prefs)).active() }.isFailure)
        assertNotEquals(durable, prefs.all) // Android mutates memory before reporting failed disk I/O.
        assertEquals(durable, prefs.disk)
        assertTrue(runCatching { renew(store(prefs)).active() }.isFailure)
        assertEquals(0, requests)
        assertNull(store(preferences(prefs.disk)).load()!!.pendingRefreshToken)
        prefs.fail = false
        renew(store(prefs)).active()
        assertEquals(1, requests)
        assertEquals("new-access", store(preferences(prefs.disk)).load()!!.token)
    }

    @Test fun `failed final write retains durable replacement across instances and process recreation`() = runBlocking {
        val prefs = preferences()
        val original = Pairing("https://example.com", "old-access", refreshToken = "r".repeat(43))
        store(prefs).save(original)
        var replacement: String? = null
        val first = store(prefs)
        val renew = TokenRenewal(first::load, first::save, { _, token ->
            replacement = token
            prefs.fail = true
            TokenResponse("new-access", token, 900, "Bearer", "health-sync:steps")
        }, { 1000 })
        assertTrue(runCatching { renew.active() }.isFailure)
        assertEquals(original.copy(pendingRefreshToken = replacement), store(prefs).load())
        val recreated = store(preferences(prefs.disk))
        assertEquals(store(prefs).load(), recreated.load())
        prefs.fail = false
        for (current in listOf(store(prefs), recreated)) {
            val retried = TokenRenewal(current::load, current::save, { pairing, token ->
                assertEquals(original.refreshToken, pairing.refreshToken)
                assertEquals(replacement, token)
                TokenResponse("new-access", token, 900, "Bearer", "health-sync:steps")
            }, { 1000 }).active()
            assertNull(retried.pendingRefreshToken)
            assertEquals(replacement, retried.refreshToken)
        }
    }

    @Test fun `failed browser state write and clear do not replace durable state`() {
        val prefs = preferences()
        val current = store(prefs)
        val pending = BrowserSignIn.start("https://example.com", "Phone", "com.nutrition.healthsync", 1000)
        current.savePending(pending)
        current.save(Pairing("https://example.com", "old-access"))
        prefs.fail = true
        assertTrue(runCatching { current.savePending(null) }.isFailure)
        assertEquals(pending.verifier, store(prefs).pending()?.verifier)
        assertTrue(runCatching { current.clear() }.isFailure)
        assertNotNull(store(prefs).load())
        assertEquals(pending.state, store(preferences(prefs.disk)).pending()?.state)
        prefs.fail = false
        current.clear()
        assertNull(store(preferences(prefs.disk)).load())
    }
}

/** Reproduces SharedPreferences.commit: memory changes even when disk does not. */
private class FaultPreferences(private val memory: SharedPreferences) : SharedPreferences by memory {
    var fail = false
    var disk: Map<String, *> = memory.all.toMap()
        private set

    override fun edit(): SharedPreferences.Editor {
        val editor = memory.edit()
        return object : SharedPreferences.Editor by editor {
            override fun putString(key: String, value: String?): SharedPreferences.Editor { editor.putString(key, value); return this }
            override fun remove(key: String): SharedPreferences.Editor { editor.remove(key); return this }
            override fun clear(): SharedPreferences.Editor { clearedNonempty = memory.all.isNotEmpty(); editor.clear(); return this }
            private var clearedNonempty = false
            override fun commit(): Boolean {
                val before = memory.all.toMap()
                editor.commit()
                // Android skips disk I/O on a no-op, even after failed writes.
                if (!clearedNonempty && before == memory.all) return true
                if (fail) return false
                disk = memory.all.toMap()
                return true
            }
        }
    }
}
