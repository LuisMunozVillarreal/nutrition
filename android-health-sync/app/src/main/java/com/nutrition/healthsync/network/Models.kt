package com.nutrition.healthsync.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

object HealthSyncJson {
    val codec = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        encodeDefaults = true
    }
}

@Serializable
data class PairRequest(
    val code: String,
    @SerialName("device_name") val deviceName: String,
)

@Serializable
data class PairResponse(val token: String)

@Serializable
data class StepsUploadRequest(val records: List<StepUploadRecord>)

@Serializable
data class StepsUploadResponse(val summary: StepsUploadSummary)

@Serializable
data class StepsUploadSummary(
    val created: Int,
    val updated: Int,
    val unchanged: Int,
    val skipped: Int,
) {
    val processed: Int
        get() = created + updated + unchanged
}

@Serializable
data class StepUploadRecord(
    val date: String,
    val steps: Long,
    @SerialName("observed_at") val observedAt: String,
)

@Serializable
data class ActivitiesUploadRequest(val records: List<ActivityUploadRecord>)

@Serializable
data class ActivitiesUploadResponse(val summary: StepsUploadSummary)

@Serializable
data class ActivityUploadRecord(
    @SerialName("source_record_id") val sourceRecordId: String,
    @SerialName("source_modified_at") val sourceModifiedAt: String,
    @SerialName("start_time") val startTime: String,
    @SerialName("end_time") val endTime: String,
    val type: String,
    @SerialName("active_kcals") val activeKcals: Int,
    @SerialName("distance_km") val distanceKm: Double?,
)