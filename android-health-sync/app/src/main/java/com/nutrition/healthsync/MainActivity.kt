package com.nutrition.healthsync

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.health.connect.client.HealthConnectClient
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.snackbar.Snackbar
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.sync.PeriodicSyncScheduler
import com.nutrition.healthsync.sync.SyncCoordinator
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlinx.coroutines.launch

fun formatInstalledVersion(versionName: String, versionCode: Int): String =
    "Version $versionName ($versionCode)"

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
    private var busy = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.activity_main)
        rootView = findViewById(android.R.id.content)
        syncButton = findViewById(R.id.btn_sync)
        syncProgress = findViewById(R.id.progress_sync)
        statusText = findViewById(R.id.text_status)
        lastSyncText = findViewById(R.id.text_last_sync)
        healthStateText = findViewById(R.id.text_health_state)
        pairingStateText = findViewById(R.id.text_pairing_state)
        backgroundStateText = findViewById(R.id.text_background_state)

        val toolbar = findViewById<MaterialToolbar>(R.id.top_app_bar)
        applyTopInset(toolbar)
        applyBottomInset(findViewById(R.id.main_scroll))
        toolbar.setOnMenuItemClickListener { item ->
            if (item.itemId != R.id.action_settings) return@setOnMenuItemClickListener false
            startActivity(Intent(this, SettingsActivity::class.java))
            true
        }
        syncButton.setOnClickListener { manualSync() }

        if (intent.action == ACTION_SHOW_PERMISSIONS_RATIONALE) showPrivacy()
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
            val hasSteps = HealthConnectDataSource.READ_STEPS in permissions
            val hasBackground = HealthConnectDataSource.READ_IN_BACKGROUND in permissions

            syncButton.isEnabled = !busy && available && hasSteps && paired
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
            lastSyncText.text = coordinator.lastSync()?.let { raw ->
                formatLastSync(raw, ZoneId.systemDefault(), Locale.ENGLISH)
            } ?: getString(R.string.last_sync_never)

            PeriodicSyncScheduler.reconcile(this@MainActivity)
            message?.let(::showMessage)
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

    private fun showPrivacy() {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.privacy_title)
            .setMessage(R.string.privacy_message)
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }

    private fun setBusy(value: Boolean) {
        busy = value
        syncProgress.visibility = if (value) View.VISIBLE else View.GONE
        if (value) syncButton.isEnabled = false
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
            val bottom = insets.getInsets(WindowInsetsCompat.Type.navigationBars()).bottom
            view.setPadding(view.paddingLeft, view.paddingTop, view.paddingRight, initialBottom + bottom)
            insets
        }
        ViewCompat.requestApplyInsets(scrollView)
    }

    private companion object {
        const val ACTION_SHOW_PERMISSIONS_RATIONALE = "androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE"
    }
}
