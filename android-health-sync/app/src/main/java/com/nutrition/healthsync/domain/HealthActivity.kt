package com.nutrition.healthsync.domain

import com.nutrition.healthsync.network.ActivityUploadRecord
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
        require(type in SUPPORTED_TYPES) { "El tipo de actividad no es compatible" }
        require(activeKcals >= 0) { "Las calorías activas no pueden ser negativas" }
        require(distanceKm == null || (distanceKm.isFinite() && distanceKm >= 0.0)) {
            "La distancia no puede ser negativa"
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
    }
}