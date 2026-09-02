package com.nutrition.healthsync.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.metadata.DataOrigin
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.AggregateGroupByPeriodRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.nutrition.healthsync.domain.DailySteps
import com.nutrition.healthsync.domain.HealthActivity
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.Period
import java.time.ZoneId
import kotlin.math.roundToInt

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

    suspend fun readGarminActivities(
        lookbackDays: Long = DEFAULT_LOOKBACK_DAYS,
    ): List<HealthActivity> {
        require(lookbackDays in 1..DEFAULT_LOOKBACK_DAYS) {
            "La ventana debe estar entre 1 y $DEFAULT_LOOKBACK_DAYS días"
        }
        val endExclusive = Instant.now()
        val start = endExclusive.minus(Duration.ofDays(lookbackDays))
        val garminOrigin = DataOrigin(GARMIN_PACKAGE)
        val sessions = keepNonOverlapping(
            readAllPages { pageToken ->
                val response = client().readRecords(
                    ReadRecordsRequest(
                        recordType = ExerciseSessionRecord::class,
                        timeRangeFilter = TimeRangeFilter.between(start, endExclusive),
                        dataOriginFilter = setOf(garminOrigin),
                        pageSize = MAX_ACTIVITY_RECORDS,
                        pageToken = pageToken,
                    ),
                )
                RecordPage(response.records, response.pageToken)
            },
            startOf = ExerciseSessionRecord::startTime,
            endOf = ExerciseSessionRecord::endTime,
            isEligible = { session ->
                val duration = Duration.between(session.startTime, session.endTime)
                GarminExerciseType.toNutritionType(session.exerciseType) != null &&
                    duration > Duration.ZERO && duration <= MAX_ACTIVITY_DURATION
            },
        )

        return sessions.mapNotNull { session ->
            val type = GarminExerciseType.toNutritionType(session.exerciseType)
                ?: return@mapNotNull null
            val totals = client().aggregate(
                AggregateRequest(
                    metrics = setOf(
                        ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL,
                        DistanceRecord.DISTANCE_TOTAL,
                    ),
                    timeRangeFilter = TimeRangeFilter.between(
                        session.startTime,
                        session.endTime,
                    ),
                    dataOriginFilter = setOf(session.metadata.dataOrigin),
                ),
            )
            val activeKcals = totals[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]
                ?.inKilocalories
                ?.roundToInt()
                ?: return@mapNotNull null
            runCatching {
                HealthActivity(
                    sourceRecordId = session.metadata.id,
                    sourceModifiedAt = session.metadata.lastModifiedTime,
                    startTime = session.startTime,
                    endTime = session.endTime,
                    type = type,
                    activeKcals = activeKcals,
                    distanceKm = totals[DistanceRecord.DISTANCE_TOTAL]?.inKilometers,
                    startZoneOffset = session.startZoneOffset
                        ?: ZoneId.systemDefault().rules.getOffset(session.startTime),
                    endZoneOffset = session.endZoneOffset
                        ?: ZoneId.systemDefault().rules.getOffset(session.endTime),
                )
            }.getOrNull()
        }
    }

    companion object {
        const val DEFAULT_LOOKBACK_DAYS = 30L
        const val GARMIN_PACKAGE = "com.garmin.android.apps.connectmobile"
        private const val MAX_ACTIVITY_RECORDS = 1000
        private val MAX_ACTIVITY_DURATION: Duration = Duration.ofHours(24)
        val READ_STEPS: String = HealthPermission.getReadPermission(StepsRecord::class)
        val READ_EXERCISE: String = HealthPermission.getReadPermission(ExerciseSessionRecord::class)
        val READ_ACTIVE_CALORIES: String =
            HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class)
        val READ_DISTANCE: String = HealthPermission.getReadPermission(DistanceRecord::class)
        val ACTIVITY_READ_PERMISSIONS: Set<String> = setOf(
            READ_EXERCISE,
            READ_ACTIVE_CALORIES,
            READ_DISTANCE,
        )
        val REQUIRED_READ_PERMISSIONS: Set<String> = ACTIVITY_READ_PERMISSIONS + READ_STEPS
        val READ_IN_BACKGROUND: String = HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND
    }
}