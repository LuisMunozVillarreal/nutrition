package com.nutrition.healthsync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class BuildProfileTest {
    @Test
    fun `production and testing profiles use isolated Android identities`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val expectedId = if (BuildConfig.IS_TESTING) {
            "com.nutrition.healthsync.testing"
        } else {
            "com.nutrition.healthsync"
        }
        val expectedName = if (BuildConfig.IS_TESTING) "Nutrition Test" else "Nutrition"

        assertEquals(expectedId, BuildConfig.APPLICATION_ID)
        assertEquals(expectedName, context.getString(R.string.app_name))
    }
}