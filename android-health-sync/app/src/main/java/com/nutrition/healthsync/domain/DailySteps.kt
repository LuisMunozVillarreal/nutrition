package com.nutrition.healthsync.domain

import com.nutrition.healthsync.network.StepUploadRecord
import java.time.Instant
import java.time.LocalDate

data class DailySteps(
    val date: LocalDate,
    val steps: Long,
) {
    init {
        require(steps >= 0) { "El conteo de pasos no puede ser negativo" }
    }

    fun toUploadRecord(observedAt: Instant): StepUploadRecord = StepUploadRecord(
        date = date.toString(),
        steps = steps,
        observedAt = observedAt.toString(),
    )
}