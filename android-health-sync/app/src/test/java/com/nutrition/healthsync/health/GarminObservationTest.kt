package com.nutrition.healthsync.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.aggregate.AggregationResult
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.health.connect.client.response.ReadRecordsResponse
import androidx.test.core.app.ApplicationProvider
import com.nutrition.healthsync.network.ActivitiesUploadRequest
import com.nutrition.healthsync.network.HealthSyncJson
import java.lang.reflect.Proxy
import java.time.Instant
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.Implementation
import org.robolectric.annotation.Implements

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], shadows = [ObservationProvider::class], instrumentedPackages = ["com.nutrition.healthsync.health"])
class GarminObservationTest {

    @Test fun `two reads preserve session version and independently order delayed aggregates`() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val source = HealthConnectDataSource(context)
        val session = ExerciseSessionRecord(
            startTime = Instant.parse("2026-09-02T09:00:00Z"), startZoneOffset = null,
            endTime = Instant.parse("2026-09-02T09:30:00Z"), endZoneOffset = null,
            exerciseType = ExerciseSessionRecord.EXERCISE_TYPE_RUNNING,
            metadata = Metadata.manualEntryWithId("session"),
        )
        var calories = 300.0
        var distance: Double? = null
        var readStarted = Instant.EPOCH
        val enclosing = ExerciseSessionRecord(
            startTime = session.startTime.minusSeconds(900), startZoneOffset = null,
            endTime = session.endTime.plusSeconds(900), endZoneOffset = null,
            exerciseType = session.exerciseType,
            metadata = Metadata.manualEntryWithId("enclosing"),
        )
        ObservationProvider.provider = Proxy.newProxyInstance(
            HealthConnectClient::class.java.classLoader, arrayOf(HealthConnectClient::class.java),
        ) { _, method, args ->
            when (method.name) {
                "readRecords" -> {
                    readStarted = Instant.now()
                    val request = args!![0] as ReadRecordsRequest<*>
                    assertEquals(setOf(HealthConnectDataSource.GARMIN_PACKAGE), request.dataOriginFilter.map { it.packageName }.toSet())
                    when (request.pageToken) {
                        null -> ReadRecordsResponse(listOf(session), if (distance == null) null else "page-2")
                        "page-2" -> ReadRecordsResponse(listOf(enclosing), null)
                        else -> error("Unexpected continuation")
                    }
                }
                "aggregate" -> {
                    val request = args!![0] as AggregateRequest
                    assertTrue(listOf(session, enclosing).any { candidate ->
                        request == AggregateRequest(
                            metrics = setOf(ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL, DistanceRecord.DISTANCE_TOTAL),
                            timeRangeFilter = TimeRangeFilter.between(candidate.startTime, candidate.endTime),
                            dataOriginFilter = setOf(candidate.metadata.dataOrigin),
                        )
                    })
                    val values = mutableMapOf(ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL.metricKey to calories)
                    distance?.let { values[DistanceRecord.DISTANCE_TOTAL.metricKey] = it }
                    AggregationResult(emptyMap(), values, emptySet())
                }
                else -> error("Unexpected provider call ${method.name}")
            }
        } as HealthConnectClient
        fun json(record: com.nutrition.healthsync.domain.HealthActivity) = HealthSyncJson.codec.parseToJsonElement(
            HealthSyncJson.codec.encodeToString(ActivitiesUploadRequest(listOf(record.toUploadRecord()))),
        ).jsonObject["records"]!!.jsonArray.single().jsonObject

        val first = source.readGarminActivities().single()
        val firstRead = readStarted
        calories = 450.0
        distance = 5500.0
        val secondRead = source.readGarminActivities()
        assertEquals("Send all valid envelopes so the persisted winner can refresh", 2, secondRead.size)
        val second = secondRead.single { it.sourceRecordId == "session" }
        assertEquals(300, first.activeKcals)
        assertNull(first.distanceKm)
        assertEquals(450, second.activeKcals)
        assertEquals(5.5, second.distanceKm!!, 0.0)
        assertEquals(first.sourceModifiedAt, second.sourceModifiedAt)
        val firstObservation = json(first)["observed_at"]
        assertNotNull("Aggregate reads need their own ordered observation", firstObservation)
        val firstTime = Instant.parse(firstObservation!!.jsonPrimitive.content)
        val secondTime = Instant.parse(json(second)["observed_at"]!!.jsonPrimitive.content)
        assertTrue(firstTime <= firstRead)
        assertTrue(secondTime <= readStarted)
        assertTrue(secondTime > firstTime)
    }
}

@Implements(HealthConnectDataSource::class, isInAndroidSdk = false)
class ObservationProvider {
    @Implementation fun client(): HealthConnectClient = provider
    companion object { lateinit var provider: HealthConnectClient }
}
