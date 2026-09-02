package com.nutrition.healthsync.health

import java.time.Instant

internal fun <T> keepNonOverlapping(
    records: List<T>,
    startOf: (T) -> Instant,
    endOf: (T) -> Instant,
    isEligible: (T) -> Boolean = { true },
): List<T> {
    val accepted = mutableListOf<T>()
    var acceptedEnd: Instant? = null
    records.filter(isEligible).sortedWith(compareBy(startOf).thenBy(endOf)).forEach { record ->
        val start = startOf(record)
        if (acceptedEnd == null || start >= acceptedEnd) {
            accepted += record
            acceptedEnd = endOf(record)
        }
    }
    return accepted
}

internal suspend fun <I, O> mapValidNonOverlapping(
    records: List<I>,
    transform: suspend (I) -> O?,
    startOf: (O) -> Instant,
    endOf: (O) -> Instant,
): List<O> {
    val valid = mutableListOf<O>()
    records.forEach { record -> transform(record)?.let(valid::add) }
    return keepNonOverlapping(valid, startOf, endOf)
}