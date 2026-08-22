package com.nutrition.healthsync.sync

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PairingOperationGuardTest {
    @Test
    fun `unpair invalidates an in-flight pairing response`() {
        val guard = PairingOperationGuard()
        val operation = guard.snapshot()

        assertTrue(guard.isCurrent(operation))
        guard.invalidate()
        assertFalse(guard.isCurrent(operation))
        assertTrue(guard.isCurrent(guard.snapshot()))
    }
}