package com.nutrition.healthsync.sync

import android.content.Context
import androidx.core.content.edit
import com.nutrition.healthsync.domain.EndpointConfig
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.network.ApiException
import com.nutrition.healthsync.network.HealthSyncApi
import com.nutrition.healthsync.storage.Pairing
import com.nutrition.healthsync.storage.SecurePairingStore
import java.time.Instant

class SyncCoordinator(context: Context) {
    private val applicationContext = context.applicationContext
    private val pairingStore = SecurePairingStore(applicationContext)
    private val health = HealthConnectDataSource(applicationContext)
    private val api = HealthSyncApi()
    private val statusStore = applicationContext.getSharedPreferences(STATUS_PREFERENCES, Context.MODE_PRIVATE)

    suspend fun pair(baseUrlInput: String, code: String, deviceName: String): Pairing {
        val baseUrl = EndpointConfig.normalize(baseUrlInput)
        require(code.trim().matches(Regex("\\d{12}"))) {
            "El código de vinculación debe tener 12 dígitos"
        }
        require(deviceName.isNotBlank()) { "Introduce el nombre del dispositivo" }
        val response = api.pair(baseUrl, code.trim(), deviceName.trim())
        return Pairing(baseUrl, response.token).also(pairingStore::save)
    }

    suspend fun syncNow(requireBackgroundPermission: Boolean = false): SyncResult {
        val pairing = pairingStore.load() ?: throw SyncException("Vincula el dispositivo primero")
        if (!health.isAvailable()) throw SyncException("Health Connect no está disponible")
        val granted = health.grantedPermissions()
        if (HealthConnectDataSource.READ_STEPS !in granted) {
            throw SyncException("Concede permiso para leer pasos")
        }
        if (requireBackgroundPermission && HealthConnectDataSource.READ_IN_BACKGROUND !in granted) {
            throw SyncException("Falta el permiso de lectura en segundo plano")
        }

        val observedAt = Instant.now()
        val records = health.readDailySteps().map { it.toUploadRecord(observedAt) }
        if (records.isEmpty()) return SyncResult(0, 0, observedAt)
        val summary = try {
            api.uploadSteps(pairing.baseUrl, pairing.token, records).summary
        } catch (error: ApiException) {
            if (error.statusCode == 401) {
                clearPairing()
                PeriodicSyncScheduler.cancel(applicationContext)
                throw SyncException(
                    "La vinculación venció o fue revocada. Vincula el dispositivo de nuevo.",
                    error,
                )
            }
            throw error
        }
        statusStore.edit {
            putString(KEY_LAST_SYNC, observedAt.toString())
            putInt(KEY_LAST_COUNT, summary.processed)
        }
        return SyncResult(summary.processed, summary.skipped, observedAt)
    }

    fun pairing(): Pairing? = pairingStore.load()

    fun clearPairing() {
        pairingStore.clear()
        statusStore.edit { clear() }
    }

    fun lastSync(): String? = statusStore.getString(KEY_LAST_SYNC, null)

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

class SyncException(message: String, cause: Throwable? = null) : Exception(message, cause)