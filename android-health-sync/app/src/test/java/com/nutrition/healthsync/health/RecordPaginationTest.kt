package com.nutrition.healthsync.health

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test

class RecordPaginationTest {
    @Test
    fun `collects every page until the continuation token is absent`() = runBlocking {
        val requestedTokens = mutableListOf<String?>()

        val records = readAllPages { token ->
            requestedTokens += token
            when (token) {
                null -> RecordPage(listOf(1, 2), "next")
                "next" -> RecordPage(listOf(3), null)
                else -> error("unexpected token")
            }
        }

        assertEquals(listOf(null, "next"), requestedTokens)
        assertEquals(listOf(1, 2, 3), records)
    }

    @Test
    fun `stops safely when a provider repeats a continuation token`() = runBlocking {
        var calls = 0

        val records = readAllPages { token ->
            calls += 1
            if (token == null) RecordPage(listOf(1), "repeat")
            else RecordPage(listOf(2), "repeat")
        }

        assertEquals(2, calls)
        assertEquals(listOf(1, 2), records)
    }
}
