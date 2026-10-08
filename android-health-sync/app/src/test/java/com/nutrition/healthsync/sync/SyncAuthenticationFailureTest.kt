package com.nutrition.healthsync.sync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import com.nutrition.healthsync.TestKeyProvider
import com.nutrition.healthsync.domain.DailySteps
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.network.ApiException
import com.nutrition.healthsync.network.HealthSyncApi
import com.nutrition.healthsync.storage.Pairing
import com.nutrition.healthsync.storage.SecurePairingStore
import java.security.Security
import java.time.LocalDate
import java.util.concurrent.TimeUnit
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
@Config(sdk = [35], shadows = [AvailableHealthData::class], instrumentedPackages = ["com.nutrition.healthsync.health"])
class SyncAuthenticationFailureTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private lateinit var store: SecurePairingStore

    @Before fun setup() {
        Security.addProvider(TestKeyProvider())
        store = SecurePairingStore(context)
        store.clear()
        WorkManagerTestInitHelper.initializeTestWorkManager(
            context, Configuration.Builder().setExecutor(SynchronousExecutor()).build(),
        )
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PeriodicSyncScheduler.UNIQUE_WORK_NAME, ExistingPeriodicWorkPolicy.UPDATE,
            PeriodicWorkRequestBuilder<StepsSyncWorker>(12, TimeUnit.HOURS)
                .setInitialDelay(12, TimeUnit.HOURS).build(),
        ).result.get()
    }

    @After fun cleanup() {
        store.clear()
        WorkManagerTestInitHelper.closeWorkDatabase()
        Security.removeProvider("AccountStateTestKeys")
    }

    @Test fun `step validation 400 does not cancel future sync or demand sign in`() = runBlocking {
        store.save(Pairing("https://example.com", "valid-access"))
        val calls = mutableListOf<String>()
        val coordinator = coordinator(calls, 400)
        val failure = runCatching { coordinator.syncNow() }.exceptionOrNull()
        assertEquals(listOf("/api/health-sync/steps/"), calls)
        assertTrue("Upload rejection must remain a validation error", failure is ApiException)
        assertEquals(400, (failure as ApiException).statusCode)
        assertFalse(store.load()!!.signInRequired)
        assertEquals(WorkInfo.State.ENQUEUED, workState())
    }

    @Test fun `upload validation after silent renewal keeps the new credential and periodic work`() = runBlocking {
        store.save(Pairing("https://example.com", "expired-access", refreshToken = "r".repeat(43)))
        val calls = mutableListOf<String>()
        val failure = runCatching { coordinator(calls, 400, renewSuccessfully = true).syncNow() }.exceptionOrNull()
        assertEquals(listOf("/api/health-sync/token/", "/api/health-sync/steps/"), calls)
        assertTrue(failure is ApiException)
        assertEquals(400, (failure as ApiException).statusCode)
        assertEquals("nhs_new-access", store.load()!!.token)
        assertFalse(store.load()!!.signInRequired)
        assertNull(store.load()!!.pendingRefreshToken)
        assertEquals(WorkInfo.State.ENQUEUED, workState())
    }

    @Test fun `invalid renewal cancels future sync while retaining recovery credentials`() = runBlocking {
        store.save(Pairing("https://example.com", "expired-access", refreshToken = "r".repeat(43)))
        val calls = mutableListOf<String>()
        val failure = runCatching { coordinator(calls, 400).syncNow() }.exceptionOrNull()
        assertEquals(listOf("/api/health-sync/token/"), calls)
        assertTrue(failure is SyncException)
        assertTrue(store.load()!!.signInRequired)
        assertEquals("r".repeat(43), store.load()!!.refreshToken)
        assertEquals(WorkInfo.State.CANCELLED, workState())
    }

    private fun workState() = WorkManager.getInstance(context)
        .getWorkInfosForUniqueWork(PeriodicSyncScheduler.UNIQUE_WORK_NAME).get().single().state

    private fun coordinator(calls: MutableList<String>, status: Int, renewSuccessfully: Boolean = false): SyncCoordinator {
        val api = HealthSyncApi(OkHttpClient.Builder().addInterceptor { chain ->
            calls.add(chain.request().url.encodedPath)
            val isRenewal = renewSuccessfully && chain.request().url.encodedPath.endsWith("/token/")
            val body = if (isRenewal) {
                val buffer = okio.Buffer()
                chain.request().body!!.writeTo(buffer)
                val replacement = org.json.JSONObject(buffer.readUtf8()).getString("next_refresh_token")
                """{"access_token":"nhs_new-access","refresh_token":"$replacement","expires_in":900,"token_type":"Bearer","scope":"health-sync:steps"}"""
            } else """{"error":"invalid_grant"}"""
            Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1)
                .code(if (isRenewal) 200 else status).message("Response").body(body.toResponseBody()).build()
        }.build())
        return SyncCoordinator(context).also {
            it.javaClass.getDeclaredField("api").apply { isAccessible = true }.set(it, api)
        }
    }
}

/** Replace only the OS Health Connect boundary; exercise real coordinator, HTTP and persistence. */
@Implements(HealthConnectDataSource::class, isInAndroidSdk = false)
class AvailableHealthData {
    @Implementation fun isAvailable() = true
    @Implementation fun grantedPermissions(continuation: Continuation<Set<String>>): Any = setOf(HealthConnectDataSource.READ_STEPS)
    @Implementation fun readDailySteps(lookbackDays: Long, continuation: Continuation<List<DailySteps>>): Any = listOf(DailySteps(LocalDate.now(), 123))
}
