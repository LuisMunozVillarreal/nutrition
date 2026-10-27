package com.nutrition.healthsync.sync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.nutrition.healthsync.TestKeyProvider
import com.nutrition.healthsync.domain.DailySteps
import com.nutrition.healthsync.domain.HealthActivity
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.network.HealthSyncApi
import com.nutrition.healthsync.storage.Pairing
import com.nutrition.healthsync.storage.SecurePairingStore
import java.security.Security
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import kotlin.coroutines.Continuation
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.Implementation
import org.robolectric.annotation.Implements

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], shadows = [GarminHealthData::class], instrumentedPackages = ["com.nutrition.healthsync.health"])
class GarminSyncIntegrationTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private lateinit var store: SecurePairingStore

    @Before fun setup() {
        Security.addProvider(TestKeyProvider())
        store = SecurePairingStore(context)
        store.clear()
        store.save(Pairing("https://example.com", "valid-access"))
        GarminHealthData.permissions = HealthConnectDataSource.REQUIRED_READ_PERMISSIONS
        GarminHealthData.stepReads = 0
        GarminHealthData.activityReads = 0
    }

    @After fun cleanup() {
        store.clear()
        Security.removeProvider("AccountStateTestKeys")
    }

    @Test fun `permissions and privacy describe Garmin as well as steps`() {
        val privacy = context.getString(com.nutrition.healthsync.R.string.privacy_message)
        assertTrue(privacy.contains("Garmin"))
        assertTrue(privacy.contains("active calories"))
        assertTrue(privacy.contains("distance"))
        assertTrue(privacy.contains("Android Keystore"))
        assertEquals("Sync health data", context.getString(com.nutrition.healthsync.R.string.button_sync_now))
        assertTrue(context.getString(com.nutrition.healthsync.R.string.button_steps_permission).contains("activities"))
    }

    @Test fun `activity only permission uploads Garmin without reading steps`() = runBlocking {
        GarminHealthData.permissions = HealthConnectDataSource.ACTIVITY_READ_PERMISSIONS
        val calls = mutableListOf<String>()
        val result = coordinator(calls).syncNow()
        assertEquals(listOf("/api/health-sync/activities/"), calls)
        assertEquals(1, result.recordsProcessed)
        assertEquals(0, GarminHealthData.stepReads)
        assertEquals(1, GarminHealthData.activityReads)
        assertNull(store.load()!!.lastReceipt)
    }

    @Test fun `combined upload preserves the acknowledged daily step receipt`() = runBlocking {
        val calls = mutableListOf<String>()
        val result = coordinator(calls).syncNow()
        assertEquals(listOf("/api/health-sync/steps/", "/api/health-sync/activities/"), calls)
        assertEquals(2, result.recordsProcessed)
        assertEquals(123L, store.load()!!.lastReceipt!!.records.single().steps)
        assertEquals(1, store.load()!!.lastReceipt!!.processed)
    }

    @Test fun `existing step only users retain sync and receipts`() = runBlocking {
        GarminHealthData.permissions = setOf(HealthConnectDataSource.READ_STEPS)
        val calls = mutableListOf<String>()
        assertEquals(1, coordinator(calls).syncNow().recordsProcessed)
        assertEquals(listOf("/api/health-sync/steps/"), calls)
        assertEquals(0, GarminHealthData.activityReads)
        assertEquals(123L, store.load()!!.lastReceipt!!.records.single().steps)
    }

    private fun coordinator(calls: MutableList<String>): SyncCoordinator {
        val api = HealthSyncApi(OkHttpClient.Builder().addInterceptor { chain ->
            val path = chain.request().url.encodedPath
            calls.add(path)
            val records = if (path.endsWith("/steps/")) {
                """, "records":[{"date":"${LocalDate.now()}","status":"created"}]"""
            } else ""
            val body = """{"summary":{"created":1,"updated":0,"unchanged":0,"skipped":0}$records}"""
            Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1)
                .code(200).message("Response").body(body.toResponseBody()).build()
        }.build())
        return SyncCoordinator(context).also {
            it.javaClass.getDeclaredField("api").apply { isAccessible = true }.set(it, api)
        }
    }
}

/** Substitute the OS provider only, retaining HTTP, coordination and encrypted storage. */
@Implements(HealthConnectDataSource::class, isInAndroidSdk = false)
class GarminHealthData {
    @Implementation fun isAvailable() = true
    @Implementation fun grantedPermissions(continuation: Continuation<Set<String>>): Any = permissions
    @Implementation fun readDailySteps(lookbackDays: Long, continuation: Continuation<List<DailySteps>>): Any {
        stepReads++
        check(HealthConnectDataSource.READ_STEPS in permissions)
        return listOf(DailySteps(LocalDate.now(), 123))
    }
    @Implementation fun readGarminActivities(lookbackDays: Long, continuation: Continuation<List<HealthActivity>>): Any {
        activityReads++
        check(permissions.containsAll(HealthConnectDataSource.ACTIVITY_READ_PERMISSIONS))
        val now = Instant.now()
        return listOf(HealthActivity("garmin-1", now, now.minusSeconds(3600), now.minusSeconds(1800), "run", 300, 5.0, ZoneOffset.UTC, ZoneOffset.UTC))
    }
    companion object {
        var permissions = emptySet<String>()
        var stepReads = 0
        var activityReads = 0
    }
}
