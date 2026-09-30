package com.nutrition.healthsync.sync

import android.content.Context
import androidx.core.content.edit
import com.nutrition.healthsync.domain.EndpointConfig
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.network.ApiException
import com.nutrition.healthsync.network.HealthSyncApi
import com.nutrition.healthsync.network.StepUploadRecord
import com.nutrition.healthsync.network.StepsUploadResponse
import com.nutrition.healthsync.storage.Pairing
import com.nutrition.healthsync.storage.SecurePairingStore
import com.nutrition.healthsync.storage.SyncReceipt
import com.nutrition.healthsync.storage.SyncReceiptRecord
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow

internal fun buildSyncReceipt(
    sent: List<StepUploadRecord>,
    response: StepsUploadResponse,
    acknowledgedAt: Instant,
): SyncReceipt {
    val sentByDate = sent.associateBy { it.date }
    val resultsByDate = response.records.associateBy { it.date }
    require(sentByDate.size == sent.size) { "Sent records contain duplicate dates" }
    require(resultsByDate.size == response.records.size) {
        "The sync response contains duplicate dates"
    }
    require(sentByDate.keys == resultsByDate.keys) {
        "The sync response does not match the sent dates"
    }
    val allowedStatuses = setOf("created", "updated", "unchanged", "skipped")
    require(response.records.all { it.status in allowedStatuses }) {
        "The sync response contains an unknown status"
    }
    require(response.records.count { it.status != "skipped" } == response.summary.processed) {
        "The processed count does not match the record statuses"
    }
    require(response.records.count { it.status == "skipped" } == response.summary.skipped) {
        "The skipped count does not match the record statuses"
    }
    return SyncReceipt(
        acknowledgedAt = acknowledgedAt.toString(),
        records = response.records.map { result ->
            val record = checkNotNull(sentByDate[result.date])
            SyncReceiptRecord(record.date, record.steps, result.status, result.reason)
        },
        processed = response.summary.processed,
        skipped = response.summary.skipped,
    )
}

class SyncCoordinator(context: Context) {
    private val applicationContext = context.applicationContext
    private val pairingStore = SecurePairingStore(applicationContext)
    private val health = HealthConnectDataSource(applicationContext)
    private val api = HealthSyncApi()
    private val pairingGuard = PairingOperationGuard()
    private val statusStore = applicationContext.getSharedPreferences(STATUS_PREFERENCES, Context.MODE_PRIVATE)

    suspend fun pair(baseUrlInput: String, code: String, deviceName: String): Pairing {
        val operation = pairingGuard.snapshot()
        val baseUrl = EndpointConfig.normalize(baseUrlInput)
        require(code.trim().matches(Regex("\\d{12}"))) {
            "The pairing code must contain 12 digits"
        }
        require(deviceName.isNotBlank()) { "Enter a device name" }
        val response = api.pair(baseUrl, code.trim(), deviceName.trim())
        if (!pairingGuard.isCurrent(operation)) {
            throw SyncException("Pairing was cancelled before it completed")
        }
        return Pairing(baseUrl, response.token).also(pairingStore::save)
    }

    suspend fun syncNow(requireBackgroundPermission: Boolean = false): SyncResult {
        val pairing = pairingStore.load() ?: throw SyncException("Connect this device first")
        if (!health.isAvailable()) throw SyncException("Health Connect is unavailable")
        val granted = health.grantedPermissions()
        if (HealthConnectDataSource.READ_STEPS !in granted) {
            throw SyncException("Allow step access first")
        }
        if (requireBackgroundPermission && HealthConnectDataSource.READ_IN_BACKGROUND !in granted) {
            throw SyncException("Background health-data access is missing")
        }

        val observedAt = Instant.now()
        val records = health.readDailySteps().map { it.toUploadRecord(observedAt) }
        val response = try {
            api.uploadSteps(pairing.baseUrl, pairing.token, records)
        } catch (error: ApiException) {
            if (error.statusCode == 401) {
                clearPairing()
                PeriodicSyncScheduler.cancel(applicationContext)
                throw SyncException(
                    "Pairing expired or was revoked. Connect this device again.",
                    error,
                )
            }
            throw error
        }
        val receipt = runCatching {
            buildSyncReceipt(records, response, Instant.now())
        }.getOrElse { error ->
            throw SyncException("The server returned an inconsistent sync receipt", error)
        }
        try {
            pairingStore.save(
                pairing.copy(
                    lastReceipt = receipt,
                ),
            )
        } catch (error: Exception) {
            if (error is CancellationException) throw error
            throw SyncException(
                "Steps reached Nutrition, but this device could not save the sync receipt",
                error,
            )
        }
        statusStore.edit {
            putString(KEY_LAST_SYNC, receipt.acknowledgedAt)
            putInt(KEY_LAST_COUNT, response.summary.processed)
        }
        return SyncResult(response.summary.processed, response.summary.skipped, observedAt)
    }

    fun pairing(): Pairing? = pairingStore.load()

    fun clearPairing() {
        pairingGuard.invalidate()
        pairingStore.clear()
        statusStore.edit { clear() }
    }

    fun lastSync(): String? = statusStore.getString(KEY_LAST_SYNC, null)

    fun receiptUpdates(): Flow<SyncReceipt?> = pairingStore.receiptUpdates()

    data class SyncResult(
        val recordsProcessed: Int,
        val recordsSkipped: Int,
        val observedAt: Instant,
    )

    private companion object {
        const val STATUS_PREFERENCES = "health_sync_status"
        const val KEY_LAST_SYNC = "last_sync"
        const val KEY_LAST_COUNT = "last_count"
    }
}

internal class PairingOperationGuard {
    private var generation: Long = 0

    @Synchronized
    fun snapshot(): Long = generation

    @Synchronized
    fun invalidate() {
        generation += 1
    }

    @Synchronized
    fun isCurrent(operation: Long): Boolean = operation == generation
}

class SyncException(message: String, cause: Throwable? = null) : Exception(message, cause)