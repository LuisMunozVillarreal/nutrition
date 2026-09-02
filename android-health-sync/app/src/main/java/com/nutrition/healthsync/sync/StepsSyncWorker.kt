package com.nutrition.healthsync.sync

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.network.ApiException
import com.nutrition.healthsync.storage.SecurePairingStore
import java.util.concurrent.TimeUnit

internal fun ApiException.isRetryableForBackgroundSync(): Boolean =
    retryable || statusCode == 408 || statusCode == 429 || (statusCode ?: 0) >= 500

class StepsSyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result = try {
        SyncCoordinator(applicationContext).syncNow(requireBackgroundPermission = true)
        Result.success()
    } catch (error: ApiException) {
        if (error.isRetryableForBackgroundSync()) {
            Result.retry()
        } else {
            Result.failure()
        }
    } catch (_: SyncException) {
        Result.failure()
    } catch (_: SecurityException) {
        Result.failure()
    } catch (_: Exception) {
        Result.retry()
    }
}

object PeriodicSyncScheduler {
    const val UNIQUE_WORK_NAME = "health-connect-steps-periodic-sync"

    suspend fun reconcile(context: Context) {
        val applicationContext = context.applicationContext
        val workManager = WorkManager.getInstance(applicationContext)
        val health = HealthConnectDataSource(applicationContext)
        val paired = SecurePairingStore(applicationContext).load() != null
        val canRun = paired && health.supportsBackgroundRead() &&
            health.grantedPermissions().containsAll(
                HealthConnectDataSource.REQUIRED_READ_PERMISSIONS +
                    HealthConnectDataSource.READ_IN_BACKGROUND,
            )

        if (!canRun) {
            workManager.cancelUniqueWork(UNIQUE_WORK_NAME)
            return
        }

        val request = PeriodicWorkRequestBuilder<StepsSyncWorker>(12, TimeUnit.HOURS)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .build()
        workManager.enqueueUniquePeriodicWork(
            UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context.applicationContext).cancelUniqueWork(UNIQUE_WORK_NAME)
    }
}