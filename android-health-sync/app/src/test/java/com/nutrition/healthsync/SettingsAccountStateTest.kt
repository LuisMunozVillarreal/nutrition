package com.nutrition.healthsync

import android.content.Context
import android.widget.TextView
import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import com.google.android.material.button.MaterialButton
import com.nutrition.healthsync.storage.Pairing
import com.nutrition.healthsync.storage.SecurePairingStore
import java.security.Key
import java.security.KeyStoreSpi
import java.security.Provider
import java.security.Security
import java.security.cert.Certificate
import java.util.Collections
import java.util.Date
import javax.crypto.spec.SecretKeySpec
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** Real preference/encryption round trips with a JVM key, not hardware Keystore acceptance. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class SettingsAccountStateTest {
    private lateinit var store: SecurePairingStore

    @Before fun setup() {
        Security.addProvider(TestKeyProvider())
        val context = ApplicationProvider.getApplicationContext<Context>()
        store = SecurePairingStore(context)
        store.clear()
        WorkManagerTestInitHelper.initializeTestWorkManager(
            context, Configuration.Builder().setExecutor(SynchronousExecutor()).build(),
        )
    }

    @After fun cleanup() {
        store.clear()
        WorkManagerTestInitHelper.closeWorkDatabase()
        Security.removeProvider("AccountStateTestKeys")
    }

    @Test fun `connected status and sign in again restore from encrypted credentials after recreation`() {
        // Expired access tokens remain connected when a renewal credential is stored.
        store.save(Pairing("https://example.com", "test-access", refreshToken = "test-renewal", accessExpiresAt = 1))
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        fun assertConnected() {
            val activity = controller.get()
            awaitAccountStatus(activity, "Connected")
            val status = activity.findViewById<TextView>(R.id.text_account_status)
            assertEquals("Connected", status.text.toString())
            assertEquals(activity.getColor(R.color.account_connected), status.currentTextColor)
            assertEquals("Nutrition account connected", status.contentDescription)
            assertEquals("Sign in again", activity.findViewById<MaterialButton>(R.id.btn_pair).text.toString())
            assertTrue(activity.findViewById<MaterialButton>(R.id.btn_unpair).isEnabled)
        }
        assertConnected()
        controller.recreate()
        assertConnected()
        controller.pause().stop().destroy()
    }

    @Test fun `visible settings follows durable credential removal without reopening`() {
        store.save(Pairing("https://example.com", "test-access"))
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        awaitAccountStatus(controller.get(), "Connected")
        store.clear()
        awaitAccountStatus(controller.get(), "Disconnected")
        assertEquals("Sign in with Nutrition", controller.get().findViewById<MaterialButton>(R.id.btn_pair).text.toString())
        controller.pause().stop().destroy()
    }

    @Test fun `browser start and cancellation never claim a new connection`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val coordinator = com.nutrition.healthsync.sync.SyncCoordinator(context)
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        awaitAccountStatus(controller.get(), "Disconnected")
        kotlinx.coroutines.runBlocking { coordinator.beginSignIn("https://example.com", "Test phone") }
        assertEquals(com.nutrition.healthsync.storage.AccountConnection.DISCONNECTED, store.accountConnection())
        val pending = requireNotNull(store.pending())
        val callback = "${BuildConfig.APPLICATION_ID}:/oauth2redirect?error=access_denied&state=${pending.state}&issuer=https%3A%2F%2Fexample.com"
        kotlinx.coroutines.runBlocking { assertFalse(coordinator.finishSignIn(callback)) }
        assertEquals(com.nutrition.healthsync.storage.AccountConnection.DISCONNECTED, store.accountConnection())
        controller.pause().stop().destroy()
    }

    @Test fun `rejected credentials remain disconnected after a fresh activity until replaced`() {
        val pairing = Pairing("https://example.com", "test-access", refreshToken = "test-renewal", signInRequired = true)
        store.save(pairing)
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        awaitAccountStatus(controller.get(), "Disconnected")
        assertEquals("Sign in again", controller.get().findViewById<MaterialButton>(R.id.btn_pair).text.toString())
        assertEquals("https://example.com", controller.get().findViewById<android.widget.EditText>(R.id.input_endpoint).text.toString())
        assertTrue(controller.get().findViewById<MaterialButton>(R.id.btn_unpair).isEnabled)
        controller.recreate()
        awaitAccountStatus(controller.get(), "Disconnected")
        assertEquals("Sign in again", controller.get().findViewById<MaterialButton>(R.id.btn_pair).text.toString())
        store.save(pairing.copy(signInRequired = false))
        awaitAccountStatus(controller.get(), "Connected")
        controller.pause().stop().destroy()
    }

    @Test fun `rejected sign in fails before reading health data and does not retry`() {
        store.save(Pairing("https://example.com", "test-access", signInRequired = true))
        val context = ApplicationProvider.getApplicationContext<Context>()
        val error = kotlinx.coroutines.runBlocking {
            runCatching { com.nutrition.healthsync.sync.SyncCoordinator(context).syncNow() }.exceptionOrNull()
        }
        assertTrue(error is com.nutrition.healthsync.sync.SyncException)
        assertEquals("Sign in again to connect this device", error?.message)
        val worker = androidx.work.testing.TestListenableWorkerBuilder<com.nutrition.healthsync.sync.StepsSyncWorker>(context).build()
        assertEquals(androidx.work.ListenableWorker.Result.failure(), kotlinx.coroutines.runBlocking { worker.doWork() })
    }

    @Test fun `resuming settings after credentials are cleared shows disconnected without stale success`() {
        store.save(Pairing("https://example.com", "legacy-access"))
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        awaitAccountStatus(controller.get(), "Connected")
        controller.pause().stop()
        SecurePairingStore(ApplicationProvider.getApplicationContext()).clear()
        controller.start().resume()
        val activity = controller.get()
        awaitAccountStatus(activity, "Disconnected")
        assertEquals("Sign in with Nutrition", activity.findViewById<MaterialButton>(R.id.btn_pair).text.toString())
        assertFalse(activity.findViewById<MaterialButton>(R.id.btn_unpair).isEnabled)
        controller.pause().stop().destroy()
    }
}

internal fun awaitAccountStatus(activity: SettingsActivity, expected: String) {
    val status = activity.findViewById<TextView>(R.id.text_account_status)
    val deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(5)
    while (status.text.toString() != expected && System.nanoTime() < deadline) {
        org.robolectric.Shadows.shadowOf(android.os.Looper.getMainLooper()).idle()
        Thread.sleep(10)
    }
    assertEquals(expected, status.text.toString())
}

class TestKeyProvider : Provider("AccountStateTestKeys", 1.0, "Test-only AES key lookup") {
    init { put("KeyStore.AndroidKeyStore", TestKeyStore::class.java.name) }
}

class TestKeyStore : KeyStoreSpi() {
    private val key = SecretKeySpec(ByteArray(32) { 7 }, "AES")
    override fun engineGetKey(alias: String?, password: CharArray?): Key = key
    override fun engineLoad(stream: java.io.InputStream?, password: CharArray?) = Unit
    override fun engineStore(stream: java.io.OutputStream?, password: CharArray?) = Unit
    override fun engineGetCertificateChain(alias: String?): Array<Certificate>? = null
    override fun engineGetCertificate(alias: String?): Certificate? = null
    override fun engineGetCreationDate(alias: String?): Date = Date(0)
    override fun engineSetKeyEntry(alias: String?, key: Key?, password: CharArray?, chain: Array<out Certificate>?) = Unit
    override fun engineSetKeyEntry(alias: String?, key: ByteArray?, chain: Array<out Certificate>?) = Unit
    override fun engineSetCertificateEntry(alias: String?, cert: Certificate?) = Unit
    override fun engineDeleteEntry(alias: String?) = Unit
    override fun engineAliases(): java.util.Enumeration<String> = Collections.enumeration(emptyList())
    override fun engineContainsAlias(alias: String?): Boolean = true
    override fun engineSize(): Int = 1
    override fun engineIsKeyEntry(alias: String?): Boolean = true
    override fun engineIsCertificateEntry(alias: String?): Boolean = false
    override fun engineGetCertificateAlias(cert: Certificate?): String? = null
}
