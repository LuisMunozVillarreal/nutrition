package com.nutrition.healthsync.network

import okio.Buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HealthSyncRequestFactoryTest {
    @Test
    fun `pairing usa endpoint exacto y no envia autorizacion`() {
        val request = HealthSyncRequestFactory.pair(
            baseUrl = "https://example.com",
            payload = PairRequest("123456789012", "Galaxy"),
        )

        assertEquals("https://example.com/api/health-sync/pair/", request.url.toString())
        assertEquals("application/json; charset=utf-8", request.body?.contentType().toString())
        assertNull(request.header("Authorization"))
        assertEquals(
            "{\"code\":\"123456789012\",\"device_name\":\"Galaxy\"}",
            request.bodyText(),
        )
    }

    @Test
    fun `subida usa bearer scoped token y contrato exacto`() {
        val request = HealthSyncRequestFactory.steps(
            baseUrl = "https://example.com",
            token = "scoped-token",
            payload = StepsUploadRequest(
                listOf(StepUploadRecord("2026-07-30", 321, "2026-07-31T08:15:30Z")),
            ),
        )

        assertEquals("https://example.com/api/health-sync/steps/", request.url.toString())
        assertEquals("Bearer scoped-token", request.header("Authorization"))
        assertEquals(
            "{\"records\":[{\"date\":\"2026-07-30\",\"steps\":321,\"observed_at\":\"2026-07-31T08:15:30Z\"}]}",
            request.bodyText(),
        )
    }

    @Test
    fun `activities usa bearer y endpoint exacto`() {
        val request = HealthSyncRequestFactory.activities(
            baseUrl = "https://example.com",
            token = "scoped-token",
            payload = ActivitiesUploadRequest(
                listOf(
                    ActivityUploadRecord(
                        sourceRecordId = "garmin-1",
                        sourceModifiedAt = "2026-09-02T08:59:00Z",
                        startTime = "2026-09-02T09:00:00Z",
                        endTime = "2026-09-02T09:45:00Z",
                        type = "run",
                        activeKcals = 420,
                        distanceKm = 7.25,
                    ),
                ),
            ),
        )

        assertEquals("https://example.com/api/health-sync/activities/", request.url.toString())
        assertEquals("Bearer scoped-token", request.header("Authorization"))
        assertEquals("application/json; charset=utf-8", request.body?.contentType().toString())
        assertEquals(
            "{\"records\":[{\"source_record_id\":\"garmin-1\",\"source_modified_at\":\"2026-09-02T08:59:00Z\",\"start_time\":\"2026-09-02T09:00:00Z\",\"end_time\":\"2026-09-02T09:45:00Z\",\"type\":\"run\",\"active_kcals\":420,\"distance_km\":7.25}]}",
            request.bodyText(),
        )
    }

    private fun okhttp3.Request.bodyText(): String = Buffer().also { body!!.writeTo(it) }.readUtf8()
}
