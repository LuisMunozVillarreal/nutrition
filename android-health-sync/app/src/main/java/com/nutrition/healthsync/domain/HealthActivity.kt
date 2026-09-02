package com.nutrition.healthsync.domain

import com.nutrition.healthsync.network.ActivityUploadRecord
import java.time.Duration
import java.time.Instant
import java.time.ZoneOffset

data class HealthActivity(
    val sourceRecordId: String,
    val sourceModifiedAt: Instant,
    val startTime: Instant,
    val endTime: Instant,
    val type: String,
    val activeKcals: Int,
    val distanceKm: Double?,
    val startZoneOffset: ZoneOffset = ZoneOffset.UTC,
    val endZoneOffset: ZoneOffset = ZoneOffset.UTC,
) {
    init {
        require(sourceRecordId.isNotBlank()) { "La actividad debe tener un identificador" }
        require(startTime < endTime) { "La actividad debe terminar después de empezar" }
        require(Duration.between(startTime, endTime) <= MAX_DURATION) {
            "La actividad no puede durar más de 24 horas"
        }
        require(type in SUPPORTED_TYPES) { "El tipo de actividad no es compatible" }
        require(activeKcals in 0..MAX_ACTIVE_KCALS) {
            "Las calorías activas deben estar dentro del intervalo permitido"
        }
        require(
            distanceKm == null ||
                (distanceKm.isFinite() && distanceKm in 0.0..MAX_DISTANCE_KM),
        ) {
            "La distancia debe estar dentro del intervalo permitido"
        }
    }

    fun toUploadRecord(): ActivityUploadRecord = ActivityUploadRecord(
        sourceRecordId = sourceRecordId,
        sourceModifiedAt = sourceModifiedAt.toString(),
        startTime = startTime.atOffset(startZoneOffset).toString(),
        endTime = endTime.atOffset(endZoneOffset).toString(),
        type = type,
        activeKcals = activeKcals,
        distanceKm = distanceKm,
    )

    companion object {
        val SUPPORTED_TYPES = setOf("walk", "run", "cycle", "gym")
        private val MAX_DURATION: Duration = Duration.ofHours(24)
        private const val MAX_ACTIVE_KCALS = 100_000
        private const val MAX_DISTANCE_KM = 99_999_999.99
    }
}