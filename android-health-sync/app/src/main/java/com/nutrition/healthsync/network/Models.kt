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