package com.nutrition.healthsync

import android.view.View
import android.widget.EditText
import android.widget.TextView
import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.progressindicator.LinearProgressIndicator
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowDialog

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class MainActivityModernUiTest {
    @Before
    fun setUp() {
        WorkManagerTestInitHelper.initializeTestWorkManager(
            ApplicationProvider.getApplicationContext(),
            Configuration.Builder().setExecutor(SynchronousExecutor()).build(),
        )
    }

    @After
    fun tearDown() {
        WorkManagerTestInitHelper.closeWorkDatabase()
    }

    @Test
    fun `overview uses Material controls and keeps configuration out of the primary screen`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()

        assertTrue(activity.findViewById<View>(R.id.top_app_bar) is MaterialToolbar)
        assertTrue(activity.findViewById<View>(R.id.btn_sync) is MaterialButton)
        assertTrue(activity.findViewById<View>(R.id.progress_sync) is LinearProgressIndicator)
        assertNull(activity.findViewById<EditText?>(R.id.input_endpoint))
        assertNull(activity.findViewById<EditText?>(R.id.input_pairing_code))
        assertTrue(activity.findViewById<TextView>(R.id.text_status).text.length < 120)
    }

    @Test
    fun `settings and about live in the toolbar menu`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val toolbar = activity.findViewById<MaterialToolbar>(R.id.top_app_bar)

        assertTrue(toolbar.menu.findItem(R.id.action_settings).isVisible)
        assertTrue(toolbar.menu.findItem(R.id.action_about).isVisible)

        toolbar.menu.performIdentifierAction(R.id.action_settings, 0)
        val settingsDialog = requireNotNull(ShadowDialog.getLatestDialog())
        assertTrue(settingsDialog.findViewById<View>(R.id.input_endpoint) is EditText)
        settingsDialog.dismiss()

        toolbar.menu.performIdentifierAction(R.id.action_about, 0)
        val aboutDialog = requireNotNull(ShadowDialog.getLatestDialog())
        val message = aboutDialog.findViewById<TextView>(android.R.id.message).text.toString()
        assertTrue(message.contains(formatInstalledVersion(BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE)))
    }

    @Test
    fun `primary text is concise and sync is disabled until setup is complete`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val status = activity.findViewById<TextView>(R.id.text_status)
        val sync = activity.findViewById<MaterialButton>(R.id.btn_sync)

        assertTrue(status.text.length < 120)
        assertFalse(sync.isEnabled)
        assertEquals(View.GONE, activity.findViewById<View>(R.id.progress_sync).visibility)
    }

    @Test
    fun `application exposes a branded launcher icon`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()

        assertEquals(R.mipmap.ic_launcher, activity.applicationInfo.icon)
    }
}
