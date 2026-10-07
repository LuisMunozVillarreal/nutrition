package com.nutrition.healthsync

import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.ScrollView
import androidx.activity.ComponentActivity
import androidx.core.net.toUri
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.snackbar.Snackbar
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.network.ApiException
import com.nutrition.healthsync.sync.PeriodicSyncScheduler
import com.nutrition.healthsync.sync.SyncCoordinator
import kotlinx.coroutines.launch

internal fun pairingFailureMessage(error: Throwable, baseUrlInput: String): String {
    if (error !is ApiException || error.statusCode != 404) {
        return error.message ?: "Could not connect this device"
    }
    val baseUrl = baseUrlInput.trim().trimEnd('/')
    return "Health sync is not available at $baseUrl/api/health-sync/pair/. " +
        "Check the server address and confirm that Health Sync is deployed there."
}

class SettingsActivity : ComponentActivity() {
    private val health by lazy { HealthConnectDataSource(applicationContext) }
    private val coordinator by lazy { SyncCoordinator(applicationContext) }

    private lateinit var rootView: View
    private lateinit var endpointInput: EditText
    private lateinit var deviceNameInput: EditText
    private lateinit var progress: LinearProgressIndicator
    private lateinit var healthSettingsButton: MaterialButton
    private lateinit var stepsPermissionButton: MaterialButton
    private lateinit var backgroundPermissionButton: MaterialButton
    private lateinit var pairButton: MaterialButton
    private lateinit var unpairButton: MaterialButton
    private var busy = false

    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract(),
    ) { granted ->
        val message = if (HealthConnectDataSource.READ_STEPS in granted) {
            getString(R.string.message_steps_granted)
        } else {
            getString(R.string.message_steps_denied)
        }
        refreshState(message)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.activity_settings)
        rootView = findViewById(android.R.id.content)
        endpointInput = findViewById(R.id.input_endpoint)
        deviceNameInput = findViewById<EditText>(R.id.input_device_name).apply {
            imeOptions = EditorInfo.IME_ACTION_DONE
        }
        progress = findViewById(R.id.settings_progress)
        healthSettingsButton = findViewById(R.id.btn_health_settings)
        stepsPermissionButton = findViewById(R.id.btn_steps_permission)
        backgroundPermissionButton = findViewById(R.id.btn_background_permission)
        pairButton = findViewById(R.id.btn_pair)
        unpairButton = findViewById(R.id.btn_unpair)

        val toolbar = findViewById<MaterialToolbar>(R.id.settings_app_bar)
        applyTopInset(toolbar)
        applyBottomInset(findViewById(R.id.settings_scroll))
        toolbar.setNavigationOnClickListener { finish() }

        if (savedInstanceState == null) {
            coordinator.pairing()?.let { endpointInput.setText(it.baseUrl) }
            deviceNameInput.setText(
                listOf(Build.MANUFACTURER, Build.MODEL).joinToString(" ").trim(),
            )
        }

        healthSettingsButton.setOnClickListener { openHealthConnect() }
        stepsPermissionButton.setOnClickListener {
            requestPermissions(setOf(HealthConnectDataSource.READ_STEPS))
        }
        backgroundPermissionButton.setOnClickListener {
            lifecycleScope.launch {
                if (health.supportsBackgroundRead()) {
                    requestPermissions(
                        setOf(
                            HealthConnectDataSource.READ_STEPS,
                            HealthConnectDataSource.READ_IN_BACKGROUND,
                        ),
                    )
                } else {
                    showMessage(getString(R.string.message_background_unavailable))
                }
            }
        }
        pairButton.setOnClickListener { signIn() }
        unpairButton.setOnClickListener { confirmUnpair() }
        findViewById<MaterialButton>(R.id.btn_privacy).setOnClickListener { showPrivacy() }
        findViewById<MaterialButton>(R.id.btn_about).setOnClickListener { showAbout() }

        if (intent.action == ACTION_SHOW_PERMISSIONS_RATIONALE) showPrivacy()
        handleSignInIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        refreshState()
    }

    private fun refreshState(message: String? = null) {
        lifecycleScope.launch {
            val available = health.availability() == HealthConnectClient.SDK_AVAILABLE
            val permissions = if (available) health.grantedPermissions() else emptySet()
            val paired = coordinator.pairing() != null
            val supportsBackground = available && health.supportsBackgroundRead()
            val hasSteps = HealthConnectDataSource.READ_STEPS in permissions
            val hasBackground = HealthConnectDataSource.READ_IN_BACKGROUND in permissions

            stepsPermissionButton.isEnabled = !busy && available && !hasSteps
            backgroundPermissionButton.isEnabled = !busy && supportsBackground && !hasBackground
            backgroundPermissionButton.visibility = if (supportsBackground) View.VISIBLE else View.GONE
            pairButton.isEnabled = !busy
            unpairButton.isEnabled = !busy && paired
            healthSettingsButton.isEnabled = !busy
            PeriodicSyncScheduler.reconcile(this@SettingsActivity)
            message?.let(::showMessage)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleSignInIntent(intent)
    }

    private fun handleSignInIntent(incoming: Intent) {
        if (incoming.action != Intent.ACTION_VIEW) return
        val callback = incoming.dataString ?: return
        // Do not retain authorization codes in Activity state or later intents.
        incoming.data = null
        lifecycleScope.launch {
            setBusy(true)
            try {
                val connected = coordinator.finishSignIn(callback)
                PeriodicSyncScheduler.reconcile(this@SettingsActivity)
                refreshState(if (connected) getString(R.string.message_paired) else "Sign-in cancelled")
            } catch (_: Exception) {
                showMessage("Sign-in could not finish. Return to Settings and try again.")
            } finally { setBusy(false) }
        }
    }

    private fun signIn() {
        val endpoint = endpointInput.text.toString()
        val name = deviceNameInput.text.toString()
        lifecycleScope.launch {
            setBusy(true)
            try {
                val url = coordinator.beginSignIn(endpoint, name)
                // ACTION_VIEW uses the system browser, never a credential-collecting WebView.
                startActivity(Intent(Intent.ACTION_VIEW, url.toUri()).addCategory(Intent.CATEGORY_BROWSABLE))
                showMessage("Finish sign-in in your browser. You can return here to cancel or retry.")
            } catch (_: Exception) {
                showMessage("Could not open sign-in. Check the HTTPS server address and device name.")
            } finally { setBusy(false) }
        }
    }

    private fun confirmUnpair() {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.unpair_title)
            .setMessage(R.string.unpair_message)
            .setNegativeButton(R.string.button_cancel, null)
            .setPositiveButton(R.string.button_confirm_unpair) { _, _ ->
                lifecycleScope.launch {
                    setBusy(true)
                    try {
                        coordinator.disconnect()
                        PeriodicSyncScheduler.cancel(this@SettingsActivity)
                        refreshState(getString(R.string.message_unpaired))
                    } catch (_: Exception) {
                        showMessage("Could not disconnect on the server. Retry when online, or revoke this phone in Nutrition Devices.")
                    } finally { setBusy(false) }
                }
            }
            .show()
    }

    private fun showPrivacy() {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.privacy_title)
            .setMessage(R.string.privacy_message)
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }

    private fun showAbout() {
        val version = formatInstalledVersion(BuildConfig.VERSION_NAME, BuildConfig.VERSION_CODE)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.app_name)
            .setMessage(getString(R.string.about_message, version))
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }

    private fun requestPermissions(permissions: Set<String>) {
        if (health.isAvailable()) permissionLauncher.launch(permissions)
        else showMessage(getString(R.string.status_health_unavailable))
    }

    private fun openHealthConnect() {
        val intent = if (health.isAvailable()) {
            HealthConnectClient.getHealthConnectManageDataIntent(this)
        } else {
            Intent(Intent.ACTION_VIEW, "market://details?id=$HEALTH_CONNECT_PACKAGE".toUri())
        }
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            showMessage(getString(R.string.message_health_screen_missing))
        }
    }

    private fun setBusy(value: Boolean) {
        busy = value
        progress.visibility = if (value) View.VISIBLE else View.GONE
        pairButton.isEnabled = !value
        stepsPermissionButton.isEnabled = !value
        backgroundPermissionButton.isEnabled = !value
        healthSettingsButton.isEnabled = !value
        unpairButton.isEnabled = !value && coordinator.pairing() != null
    }

    private fun showMessage(message: String) {
        Snackbar.make(rootView, message, Snackbar.LENGTH_LONG).show()
    }

    private fun applyTopInset(toolbar: MaterialToolbar) {
        val initialTop = toolbar.paddingTop
        ViewCompat.setOnApplyWindowInsetsListener(toolbar) { view, insets ->
            val top = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top
            view.setPadding(view.paddingLeft, initialTop + top, view.paddingRight, view.paddingBottom)
            insets
        }
        ViewCompat.requestApplyInsets(toolbar)
    }

    private fun applyBottomInset(scrollView: ScrollView) {
        val initialBottom = scrollView.paddingBottom
        ViewCompat.setOnApplyWindowInsetsListener(scrollView) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.navigationBars())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            view.setPadding(
                view.paddingLeft,
                view.paddingTop,
                view.paddingRight,
                initialBottom + maxOf(bars.bottom, ime.bottom),
            )
            insets
        }
        ViewCompat.requestApplyInsets(scrollView)
    }

    private companion object {
        const val ACTION_SHOW_PERMISSIONS_RATIONALE = "androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE"
        const val HEALTH_CONNECT_PACKAGE = "com.google.android.apps.healthdata"
    }
}
