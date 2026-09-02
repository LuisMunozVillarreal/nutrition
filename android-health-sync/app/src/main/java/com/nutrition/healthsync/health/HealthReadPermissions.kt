package com.nutrition.healthsync.health

internal object HealthReadPermissions {
    fun canReadSteps(granted: Set<String>): Boolean =
        HealthConnectDataSource.READ_STEPS in granted

    fun canReadActivities(granted: Set<String>): Boolean = granted.containsAll(
        HealthConnectDataSource.ACTIVITY_READ_PERMISSIONS,
    )

    fun canSyncAnything(granted: Set<String>): Boolean =
        canReadSteps(granted) || canReadActivities(granted)

    fun canRunInBackground(granted: Set<String>): Boolean =
        HealthConnectDataSource.READ_IN_BACKGROUND in granted && canSyncAnything(granted)
}