package com.nutrition.healthsync.health

internal data class RecordPage<T>(
    val records: List<T>,
    val nextPageToken: String?,
)

internal suspend fun <T> readAllPages(
    fetchPage: suspend (pageToken: String?) -> RecordPage<T>,
): List<T> {
    val records = mutableListOf<T>()
    var pageToken: String? = null
    do {
        val page = fetchPage(pageToken)
        records += page.records
        pageToken = page.nextPageToken
    } while (pageToken != null)
    return records
}