package com.nutrition.healthsync.auth

import com.nutrition.healthsync.network.HealthSyncApi
import com.nutrition.healthsync.storage.Pairing
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.junit.Assert.*
import org.junit.Test

class TokenApiTest {
    @Test fun `code and renewal credentials travel only in bounded POST bodies`() = runBlocking {
        val pending = BrowserSignIn.start("https://example.com", "Phone", "com.nutrition.healthsync", 100)
        val requests = mutableListOf<String>()
        val client = OkHttpClient.Builder().addInterceptor { chain ->
            val request = chain.request()
            assertEquals("POST", request.method)
            assertEquals("https://example.com/api/health-sync/token/", request.url.toString())
            assertNull(request.header("Authorization"))
            requests += Buffer().also { request.body!!.writeTo(it) }.readUtf8()
            Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK")
                .body("""{"access_token":"nhs_access","refresh_token":"${"r".repeat(43)}","expires_in":900,"token_type":"Bearer","scope":"health-sync:steps"}""".toResponseBody()).build()
        }.build()
        val api = HealthSyncApi(client)
        api.exchangeCode(pending, "c".repeat(43))
        assertTrue(requests[0].contains(pending.verifier))
        api.refresh(Pairing(pending.baseUrl, "nhs_old", refreshToken = "r".repeat(43)), "n".repeat(43))
        assertTrue(requests[1].contains("next_refresh_token"))
        assertFalse(requests[1].contains("code_verifier"))
    }
}
