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

    private fun okhttp3.Request.bodyText(): String = Buffer().also { body!!.writeTo(it) }.readUtf8()
}
