package com.nutrition.healthsync.health

internal data class RecordPage<T>(
    val records: List<T>,
    val nextPageToken: String?,
)

internal suspend fun <T> readAllPages(
    fetchPage: suspend (pageToken: String?) -> RecordPage<T>,
): List<T> {
    val records = mutableListOf<T>()
    val seenTokens = mutableSetOf<String>()
    var pageToken: String? = null
    while (true) {
        val page = fetchPage(pageToken)
        records += page.records
        val nextPageToken = page.nextPageToken
        if (nextPageToken == null || !seenTokens.add(nextPageToken)) break
        pageToken = nextPageToken
    }
    return records
}