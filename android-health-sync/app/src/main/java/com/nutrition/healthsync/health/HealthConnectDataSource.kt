package com.nutrition.healthsync.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateGroupByPeriodRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.nutrition.healthsync.domain.DailySteps
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.Period

class HealthConnectDataSource(private val context: Context) {
    fun availability(): Int = HealthConnectClient.getSdkStatus(context)

    fun isAvailable(): Boolean = availability() == HealthConnectClient.SDK_AVAILABLE

    fun client(): HealthConnectClient {
        check(isAvailable()) { "Health Connect no está disponible" }
        return HealthConnectClient.getOrCreate(context)
    }

    fun supportsBackgroundRead(): Boolean = isAvailable() &&
        client().features.getFeatureStatus(
            HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND,
        ) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE

    suspend fun grantedPermissions(): Set<String> = if (isAvailable()) {
        client().permissionController.getGrantedPermissions()
    } else {
        emptySet()
    }

    suspend fun readDailySteps(lookbackDays: Long = DEFAULT_LOOKBACK_DAYS): List<DailySteps> {
        require(lookbackDays in 1..DEFAULT_LOOKBACK_DAYS) {
            "La ventana debe estar entre 1 y $DEFAULT_LOOKBACK_DAYS días"
        }
        val today = LocalDate.now()
        val start = LocalDateTime.of(today.minusDays(lookbackDays - 1), LocalTime.MIN)
        val endExclusive = LocalDateTime.of(today.plusDays(1), LocalTime.MIN)
        val buckets = client().aggregateGroupByPeriod(
            AggregateGroupByPeriodRequest(
                metrics = setOf(StepsRecord.COUNT_TOTAL),
                timeRangeFilter = TimeRangeFilter.between(start, endExclusive),
                timeRangeSlicer = Period.ofDays(1),
            ),
        )
        return buckets.mapNotNull { bucket ->
            bucket.result[StepsRecord.COUNT_TOTAL]?.let { count ->
                DailySteps(date = bucket.startTime.toLocalDate(), steps = count)
            }
        }
    }

    companion object {
        const val DEFAULT_LOOKBACK_DAYS = 30L
        val READ_STEPS: String = HealthPermission.getReadPermission(StepsRecord::class)
        val READ_IN_BACKGROUND: String = HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND
    }
}