package com.nutrition.healthsync.network

import com.nutrition.healthsync.auth.PendingSignIn
import com.nutrition.healthsync.storage.Pairing
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

object HealthSyncRequestFactory {
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    fun pair(baseUrl: String, payload: PairRequest): Request = Request.Builder()
        .url("$baseUrl/api/health-sync/pair/")
        .post(HealthSyncJson.codec.encodeToString(payload).toRequestBody(jsonMediaType))
        .build()

    fun steps(baseUrl: String, token: String, payload: StepsUploadRequest): Request {
        require(token.isNotBlank()) { "The pairing token is missing" }
        return Request.Builder()
            .url("$baseUrl/api/health-sync/steps/")
            .header("Authorization", "Bearer $token")
            .post(HealthSyncJson.codec.encodeToString(payload).toRequestBody(jsonMediaType))
            .build()
    }
}

class HealthSyncApi(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .callTimeout(45, TimeUnit.SECONDS)
        .build(),
) {
    private fun authRequest(baseUrl: String, action: String, payload: Map<String, String>): Request = Request.Builder()
        .url("$baseUrl/api/health-sync/$action/")
        .post(HealthSyncJson.codec.encodeToString(payload).toRequestBody("application/json; charset=utf-8".toMediaType()))
        .build()

    private suspend fun token(baseUrl: String, payload: Map<String, String>): TokenResponse =
        execute(authRequest(baseUrl, "token", payload + ("issuer" to baseUrl))) { body ->
            val response = HealthSyncJson.codec.decodeFromString<TokenResponse>(body)
            response.validate()
            response
        }

    suspend fun exchangeCode(pending: PendingSignIn, code: String): TokenResponse = token(pending.baseUrl, mapOf(
        "grant_type" to "authorization_code", "code" to code,
        "code_verifier" to pending.verifier, "redirect_uri" to pending.redirectUri,
    ))

    suspend fun refresh(pairing: Pairing, replacement: String): TokenResponse = token(pairing.baseUrl, mapOf(
        "grant_type" to "refresh_token", "refresh_token" to checkNotNull(pairing.refreshToken),
        "next_refresh_token" to replacement,
    ))

    suspend fun revoke(pairing: Pairing) {
        execute(authRequest(pairing.baseUrl, "revoke", mapOf(
            "issuer" to pairing.baseUrl, "refresh_token" to checkNotNull(pairing.refreshToken),
        ))) { Unit }
    }

    suspend fun pair(baseUrl: String, code: String, deviceName: String): PairResponse {
        val request = HealthSyncRequestFactory.pair(
            baseUrl,
            PairRequest(code = code, deviceName = deviceName),
        )
        return execute(request) { body ->
            val response = runCatching {
                HealthSyncJson.codec.decodeFromString<PairResponse>(body)
            }.getOrElse { throw ApiException("The pairing response is invalid", cause = it) }
            require(response.token.isNotBlank()) { "The server did not return a valid token" }
            response.copy(token = response.token.trim())
        }
    }

    suspend fun uploadSteps(
        baseUrl: String,
        token: String,
        records: List<StepUploadRecord>,
    ): StepsUploadResponse {
        val request = HealthSyncRequestFactory.steps(
            baseUrl,
            token,
            StepsUploadRequest(records),
        )
        return execute(request) { body ->
            runCatching {
                HealthSyncJson.codec.decodeFromString<StepsUploadResponse>(body)
            }.getOrElse {
                throw ApiException("The sync response is invalid", cause = it)
            }
        }
    }

    private suspend fun <T> execute(request: Request, read: (String) -> T): T =
        withContext(Dispatchers.IO) {
            try {
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        val retryable = response.code == 408 || response.code == 429 || response.code >= 500
                        throw ApiException(
                            message = "The server returned HTTP ${response.code}",
                            statusCode = response.code,
                            retryable = retryable,
                        )
                    }
                    val body = response.body?.string().orEmpty()
                    read(body)
                }
            } catch (error: ApiException) {
                throw error
            } catch (error: IOException) {
                throw ApiException(
                    "Could not connect to the server",
                    retryable = true,
                    cause = error,
                )
            }
        }
}

open class ApiException(
    message: String,
    val statusCode: Int? = null,
    val retryable: Boolean = false,
    cause: Throwable? = null,
) : Exception(message, cause)
