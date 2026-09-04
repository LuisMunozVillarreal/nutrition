package com.nutrition.healthsync

import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.appcompat.app.AlertDialog
import androidx.core.net.toUri
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.snackbar.Snackbar
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.sync.PeriodicSyncScheduler
import com.nutrition.healthsync.sync.SyncCoordinator
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

fun formatInstalledVersion(versionName: String, versionCode: Int): String =
    "Versión $versionName ($versionCode)"

fun formatLastSync(rawInstant: String, zoneId: ZoneId, locale: Locale): String? =
    runCatching {
        DateTimeFormatter.ofPattern("d MMM, HH:mm", locale)
            .withZone(zoneId)
            .format(Instant.parse(rawInstant))
    }.getOrNull()

class MainActivity : ComponentActivity() {
    private val health by lazy { HealthConnectDataSource(applicationContext) }
    private val coordinator by lazy { SyncCoordinator(applicationContext) }

    private lateinit var rootView: View
    private lateinit var syncButton: MaterialButton
    private lateinit var syncProgress: LinearProgressIndicator
    private lateinit var statusText: TextView
    private lateinit var lastSyncText: TextView
    private lateinit var healthStateText: TextView
    private lateinit var pairingStateText: TextView
    private lateinit var backgroundStateText: TextView

    private var settingsDialog: AlertDialog? = null
    private var endpointInput: EditText? = null
    private var codeInput: EditText? = null
    private var deviceNameInput: EditText? = null
    private var healthSettingsButton: MaterialButton? = null
    private var stepsPermissionButton: MaterialButton? = null
    private var backgroundPermissionButton: MaterialButton? = null
    private var pairButton: MaterialButton? = null
    private var unpairButton: MaterialButton? = null
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
        setContentView(R.layout.activity_main)
        rootView = findViewById(android.R.id.content)
        syncButton = findViewById(R.id.btn_sync)
        syncProgress = findViewById(R.id.progress_sync)
        statusText = findViewById(R.id.text_status)
        lastSyncText = findViewById(R.id.text_last_sync)
        healthStateText = findViewById(R.id.text_health_state)
        pairingStateText = findViewById(R.id.text_pairing_state)
        backgroundStateText = findViewById(R.id.text_background_state)

        findViewById<MaterialToolbar>(R.id.top_app_bar).setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_settings -> showSettings()
                R.id.action_privacy -> showPrivacy()
                R.id.action_about -> showAbout()
                else -> return@setOnMenuItemClickListener false
            }
            true
        }
        syncButton.setOnClickListener { manualSync() }

        if (intent.action == ACTION_SHOW_PERMISSIONS_RATIONALE) showPrivacy()
    }

    override fun onResume() {
        super.onResume()
        refreshState()
    }

    private fun showSettings() {
        if (settingsDialog?.isShowing == true) return
        val content = layoutInflater.inflate(R.layout.dialog_settings, null)
        endpointInput = content.findViewById(R.id.input_endpoint)
        codeInput = content.findViewById(R.id.input_pairing_code)
        deviceNameInput = content.findViewById<EditText>(R.id.input_device_name).apply {
            imeOptions = EditorInfo.IME_ACTION_DONE
        }
        healthSettingsButton = content.findViewById(R.id.btn_health_settings)
        stepsPermissionButton = content.findViewById(R.id.btn_steps_permission)
        backgroundPermissionButton = content.findViewById(R.id.btn_background_permission)
        pairButton = content.findViewById(R.id.btn_pair)
        unpairButton = content.findViewById(R.id.btn_unpair)

        coordinator.pairing()?.let { endpointInput?.setText(it.baseUrl) }
        deviceNameInput?.setText(
            listOf(Build.MANUFACTURER, Build.MODEL).joinToString(" ").trim(),
        )
        healthSettingsButton?.setOnClickListener { openHealthConnect() }
        stepsPermissionButton?.setOnClickListener {
            requestPermissions(setOf(HealthConnectDataSource.READ_STEPS))
        }
        backgroundPermissionButton?.setOnClickListener {
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
        pairButton?.setOnClickListener { pairDevice() }
        unpairButton?.setOnClickListener { confirmUnpair() }

        settingsDialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.settings_title)
            .setView(content)
            .setNegativeButton(R.string.button_close, null)
            .create()
            .also { dialog ->
                dialog.setOnDismissListener {
                    endpointInput = null
                    codeInput = null
                    deviceNameInput = null
                    healthSettingsButton = null
                    stepsPermissionButton = null
                    backgroundPermissionButton = null
                    pairButton = null
                    unpairButton = null
                    settingsDialog = null
                }
                dialog.show()
            }
        refreshState()
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

    private fun refreshState(message: String? = null) {
        lifecycleScope.launch {
            val availability = health.availability()
            val available = availability == HealthConnectClient.SDK_AVAILABLE
            val permissions = if (available) health.grantedPermissions() else emptySet()
            val paired = coordinator.pairing() != null
            val supportsBackground = available && health.supportsBackgroundRead()
            val hasSteps = HealthConnectDataSource.READ_STEPS in permissions
            val hasBackground = HealthConnectDataSource.READ_IN_BACKGROUND in permissions

            syncButton.isEnabled = !busy && available && hasSteps && paired
            stepsPermissionButton?.isEnabled = !busy && available && !hasSteps
            backgroundPermissionButton?.isEnabled = !busy && supportsBackground && !hasBackground
            backgroundPermissionButton?.visibility = if (supportsBackground) View.VISIBLE else View.GONE
            pairButton?.isEnabled = !busy
            unpairButton?.isEnabled = !busy && paired
            healthSettingsButton?.isEnabled = !busy

            statusText.setText(
                when {
                    !available -> R.string.status_health_unavailable
                    !hasSteps -> R.string.status_needs_steps
                    !paired -> R.string.status_needs_pairing
                    else -> R.string.status_ready
                },
            )
            healthStateText.setText(
                if (available && hasSteps) R.string.health_connected else R.string.health_needs_attention,
            )
            pairingStateText.setText(
                if (paired) R.string.server_connected else R.string.server_not_connected,
            )
            backgroundStateText.setText(
                if (hasBackground) R.string.background_enabled else R.string.background_disabled,
            )
            val readableLastSync = coordinator.lastSync()?.let { raw ->
                formatLastSync(
                    raw,
                    ZoneId.systemDefault(),
                    resources.configuration.locales[0],
                )
            }
            lastSyncText.text = readableLastSync ?: getString(R.string.last_sync_never)

            PeriodicSyncScheduler.reconcile(this@MainActivity)
            message?.let(::showMessage)
        }
    }

    private fun pairDevice() {
        val endpoint = endpointInput?.text?.toString().orEmpty()
        val code = codeInput?.text?.toString().orEmpty()
        val deviceName = deviceNameInput?.text?.toString().orEmpty()
        lifecycleScope.launch {
            setBusy(true)
            runCatching { coordinator.pair(endpoint, code, deviceName) }
                .onSuccess {
                    codeInput?.text?.clear()
                    PeriodicSyncScheduler.reconcile(this@MainActivity)
                    settingsDialog?.dismiss()
                    setBusy(false)
                    refreshState(getString(R.string.message_paired))
                }
                .onFailure { error ->
                    setBusy(false)
                    refreshState(error.message ?: getString(R.string.message_pair_failed))
                }
        }
    }

    private fun manualSync() {
        lifecycleScope.launch {
            setBusy(true)
            runCatching { coordinator.syncNow() }
                .onSuccess { result ->
                    val message = when {
                        result.recordsProcessed == 0 && result.recordsSkipped == 0 ->
                            getString(R.string.message_no_steps)
                        result.recordsSkipped > 0 -> getString(
                            R.string.message_sync_complete_skipped,
                            result.recordsProcessed,
                            result.recordsSkipped,
                        )
                        else -> getString(R.string.message_sync_complete, result.recordsProcessed)
                    }
                    setBusy(false)
                    refreshState(message)
                }
                .onFailure { error ->
                    setBusy(false)
                    refreshState(error.message ?: getString(R.string.message_sync_failed))
                }
        }
    }

    private fun confirmUnpair() {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.unpair_title)
            .setMessage(R.string.unpair_message)
            .setNegativeButton(R.string.button_cancel, null)
            .setPositiveButton(R.string.button_confirm_unpair) { _, _ ->
                coordinator.clearPairing()
                PeriodicSyncScheduler.cancel(this)
                settingsDialog?.dismiss()
                refreshState(getString(R.string.message_unpaired))
            }
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
            Intent(
                Intent.ACTION_VIEW,
                "market://details?id=$HEALTH_CONNECT_PACKAGE".toUri(),
            )
        }
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            showMessage(getString(R.string.message_health_screen_missing))
        }
    }

    private fun setBusy(value: Boolean) {
        busy = value
        syncProgress.visibility = if (value) View.VISIBLE else View.GONE
        syncButton.isEnabled = !value
        pairButton?.isEnabled = !value
        stepsPermissionButton?.isEnabled = !value
        backgroundPermissionButton?.isEnabled = !value
        healthSettingsButton?.isEnabled = !value
        unpairButton?.isEnabled = !value && coordinator.pairing() != null
    }

    private fun showMessage(message: String) {
        Snackbar.make(rootView, message, Snackbar.LENGTH_LONG).show()
    }

    private companion object {
        const val ACTION_SHOW_PERMISSIONS_RATIONALE = "androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE"
        const val HEALTH_CONNECT_PACKAGE = "com.google.android.apps.healthdata"
    }
}
