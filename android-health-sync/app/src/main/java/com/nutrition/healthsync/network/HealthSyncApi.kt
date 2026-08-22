package com.nutrition.healthsync.network

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
        require(token.isNotBlank()) { "Falta el token de vinculación" }
        return Request.Builder()
            .url("$baseUrl/api/health-sync/steps/")
            .header("Authorization", "Bearer $token")
            .post(HealthSyncJson.codec.encodeToString(payload).toRequestBody(jsonMediaType))
            .build()
    }
}

class HealthSyncApi(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .callTimeout(45, TimeUnit.SECONDS)
        .build(),
) {
    suspend fun pair(baseUrl: String, code: String, deviceName: String): PairResponse {
        val request = HealthSyncRequestFactory.pair(
            baseUrl,
            PairRequest(code = code, deviceName = deviceName),
        )
        return execute(request) { body ->
            val response = runCatching {
                HealthSyncJson.codec.decodeFromString<PairResponse>(body)
            }.getOrElse { throw ApiException("La respuesta de vinculación no es válida", cause = it) }
            require(response.token.isNotBlank()) { "El servidor no devolvió un token válido" }
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
                throw ApiException("La respuesta de sincronización no es válida", cause = it)
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
                            message = "El servidor respondió con HTTP ${response.code}",
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
                    "No se pudo conectar con el servidor",
                    retryable = true,
                    cause = error,
                )
            }
        }
}

class ApiException(
    message: String,
    val statusCode: Int? = null,
    val retryable: Boolean = false,
    cause: Throwable? = null,
) : Exception(message, cause)
