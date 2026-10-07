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
class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in") val expiresIn: Long,
    @SerialName("token_type") val tokenType: String,
    val scope: String,
) {
    fun validate() {
        require(accessToken.startsWith("nhs_") && refreshToken.matches(Regex("[A-Za-z0-9_-]{43}")) &&
            expiresIn in 1..900 && tokenType == "Bearer" && scope == "health-sync:steps") {
            "The server returned invalid sign-in credentials"
        }
    }
}

@Serializable
data class StepsUploadRequest(val records: List<StepUploadRecord>)

@Serializable
data class StepsUploadResponse(
    val summary: StepsUploadSummary,
    val records: List<StepUploadResult>,
)

@Serializable
data class StepUploadResult(
    val date: String,
    val status: String,
    val reason: String? = null,
)

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