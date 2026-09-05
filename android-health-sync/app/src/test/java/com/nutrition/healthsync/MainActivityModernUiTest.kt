package com.nutrition.healthsync

import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.graphics.Insets
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.textfield.TextInputLayout
import com.nutrition.healthsync.network.ApiException
import java.io.File
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
import org.robolectric.Shadows.shadowOf
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
        val toolbar = activity.findViewById<MaterialToolbar>(R.id.top_app_bar)

        assertTrue(toolbar is MaterialToolbar)
        assertEquals(activity.getString(R.string.app_name), toolbar.title)
        assertTrue(activity.findViewById<View>(R.id.btn_sync) is MaterialButton)
        assertTrue(activity.findViewById<View>(R.id.progress_sync) is LinearProgressIndicator)
        assertNull(activity.findViewById<EditText?>(R.id.input_endpoint))
        assertNull(activity.findViewById<EditText?>(R.id.input_pairing_code))
        assertTrue(activity.findViewById<TextView>(R.id.text_status).text.length < 120)
    }

    @Test
    fun `the visible settings action opens a full screen destination`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val toolbar = activity.findViewById<MaterialToolbar>(R.id.top_app_bar)

        assertEquals(1, toolbar.menu.size())
        assertTrue(toolbar.menu.findItem(R.id.action_settings).isVisible)

        toolbar.menu.performIdentifierAction(R.id.action_settings, 0)
        val intent = requireNotNull(shadowOf(activity).nextStartedActivity)
        assertEquals(SettingsActivity::class.java.name, intent.component?.className)
        assertNull(ShadowDialog.getLatestDialog())
    }

    @Test
    fun `settings is a full screen Material view with account and permissions controls`() {
        val activity = Robolectric.buildActivity(SettingsActivity::class.java).setup().get()
        val toolbar = activity.findViewById<MaterialToolbar>(R.id.settings_app_bar)

        assertEquals("Settings", toolbar.title)
        assertTrue(activity.findViewById<View>(R.id.input_endpoint) is EditText)
        assertTrue(activity.findViewById<View>(R.id.input_pairing_code) is EditText)
        activity.findViewById<MaterialButton>(R.id.btn_about).performClick()
        val aboutDialog = requireNotNull(ShadowDialog.getLatestDialog())
        val message = aboutDialog.findViewById<TextView>(android.R.id.message).text.toString()
        assertTrue(message.contains(formatInstalledVersion(BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE)))
    }

    @Test
    fun `settings fields use labels without overlapping edit text hints`() {
        val activity = Robolectric.buildActivity(SettingsActivity::class.java).setup().get()

        val endpointInput = activity.findViewById<EditText>(R.id.input_endpoint)
        val pairingInput = activity.findViewById<EditText>(R.id.input_pairing_code)
        val endpointLayout = endpointInput.parent.parent as TextInputLayout
        val pairingLayout = pairingInput.parent.parent as TextInputLayout
        assertEquals("Server address", endpointLayout.hint)
        assertEquals(endpointLayout.hint, endpointInput.hint)
        assertEquals(pairingLayout.hint, pairingInput.hint)
        assertFalse(endpointInput.hint.toString().contains("example.com"))
        assertTrue(endpointLayout.helperText.toString().contains("/api/health-sync/pair/"))
        assertFalse(pairingInput.hint.toString().contains("12 digits"))
        assertTrue(pairingLayout.helperText.toString().contains("Devices"))
        assertTrue(pairingLayout.helperText.toString().contains("Pair Android phone"))
    }

    @Test
    fun `pairing 404 identifies the exact server route`() {
        val message = pairingFailureMessage(
            ApiException("The server returned HTTP 404", 404),
            "https://example.com",
        )

        assertTrue(message.contains("https://example.com/api/health-sync/pair/"))
        assertTrue(message.contains("not available"))
    }

    @Test
    fun `toolbar applies the status bar inset`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val toolbar = activity.findViewById<MaterialToolbar>(R.id.top_app_bar)
        val initialTop = toolbar.paddingTop

        ViewCompat.dispatchApplyWindowInsets(
            toolbar,
            WindowInsetsCompat.Builder()
                .setInsets(WindowInsetsCompat.Type.statusBars(), Insets.of(0, 36, 0, 0))
                .build(),
        )

        assertEquals(initialTop + 36, toolbar.paddingTop)
    }

    @Test
    fun `content applies the navigation bar inset without accumulating it`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        val scrollView = descendants(content).filterIsInstance<ScrollView>().single()
        val initialBottom = scrollView.paddingBottom
        val navigationInsets = WindowInsetsCompat.Builder()
            .setInsets(WindowInsetsCompat.Type.navigationBars(), Insets.of(0, 0, 0, 48))
            .build()

        ViewCompat.dispatchApplyWindowInsets(scrollView, navigationInsets)
        ViewCompat.dispatchApplyWindowInsets(scrollView, navigationInsets)

        assertEquals(initialBottom + 48, scrollView.paddingBottom)
    }

    @Test
    fun `all shipped user messages are English`() {
        val sourceRoot = listOf(File("app/src/main"), File("src/main")).first(File::exists)
        val shippedText = sourceRoot.walkTopDown()
            .filter { it.isFile && it.extension in setOf("kt", "xml") }
            .joinToString("\n") { it.readText() }
        val spanishPhrases = listOf(
            "vinculación",
            "servidor no",
            "Concede permiso",
            "Introduce el nombre",
            "no está disponible",
            "La ventana debe",
            "no puede estar vacío",
            "No se pudo guardar",
            "El conteo de pasos",
        )

        spanishPhrases.forEach { phrase ->
            assertFalse("Found Spanish user-facing text: $phrase", shippedText.contains(phrase))
        }
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

    private fun descendants(root: View): Sequence<View> = sequence {
        yield(root)
        if (root is ViewGroup) {
            for (index in 0 until root.childCount) {
                yieldAll(descendants(root.getChildAt(index)))
            }
        }
    }
}
