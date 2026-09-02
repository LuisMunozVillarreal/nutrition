package com.nutrition.healthsync.health

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HealthReadPermissionsTest {
    @Test
    fun `step-only grant remains syncable after activity upgrade`() {
        val granted = setOf(HealthConnectDataSource.READ_STEPS)

        assertTrue(HealthReadPermissions.canReadSteps(granted))
        assertFalse(HealthReadPermissions.canReadActivities(granted))
        assertTrue(HealthReadPermissions.canSyncAnything(granted))
    }

    @Test
    fun `activities require the complete activity permission group`() {
        val partial = setOf(
            HealthConnectDataSource.READ_EXERCISE,
            HealthConnectDataSource.READ_ACTIVE_CALORIES,
        )
        val complete = partial + HealthConnectDataSource.READ_DISTANCE

        assertFalse(HealthReadPermissions.canReadActivities(partial))
        assertFalse(HealthReadPermissions.canSyncAnything(partial))
        assertTrue(HealthReadPermissions.canReadActivities(complete))
        assertTrue(HealthReadPermissions.canSyncAnything(complete))
    }

    @Test
    fun `background sync requires background grant and at least one readable category`() {
        val stepOnly = setOf(HealthConnectDataSource.READ_STEPS)

        assertFalse(HealthReadPermissions.canRunInBackground(stepOnly))
        assertTrue(
            HealthReadPermissions.canRunInBackground(
                stepOnly + HealthConnectDataSource.READ_IN_BACKGROUND,
            ),
        )
    }
}
