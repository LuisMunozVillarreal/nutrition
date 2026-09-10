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
import com.nutrition.healthsync.storage.SyncReceipt
import com.nutrition.healthsync.storage.SyncReceiptRecord
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
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

fun formatConnectionState(connected: Boolean): String =
    if (connected) "DEVICE CONNECTED" else "DEVICE NOT CONNECTED"

fun formatRecordStatus(status: String, reason: String?): String = when (status) {
    "created" -> "Added"
    "updated" -> "Updated"
    "unchanged" -> "Already up to date"
    "skipped" -> when (reason) {
        "missing_plan_day" -> "No plan day for this date"
        "ambiguous_plan_day" -> "Duplicate plan days for this date"
        "day_changed_retry" -> "Changed during sync, try again"
        else -> "Not synced"
    }
    else -> "Unknown"
}

fun formatSkippedSummary(records: List<SyncReceiptRecord>): String? {
    val skipped = records.filter { it.status == "skipped" }
    if (skipped.isEmpty()) return null
    val knownReasons = setOf("missing_plan_day", "ambiguous_plan_day", "day_changed_retry")
    val explanations = listOf(
        "missing_plan_day" to "no plan day for this date — add it in Nutrition",
        "ambiguous_plan_day" to "duplicate plan days for this date — keep one in Nutrition",
        "day_changed_retry" to "changed during sync — try again",
    )
    val lines = buildList {
        for ((reason, explanation) in explanations) {
            val count = skipped.count { it.reason == reason }
            if (count > 0) {
                add("$count ${if (count == 1) "day" else "days"} skipped: $explanation")
            }
        }
        val unknown = skipped.count { it.reason !in knownReasons }
        if (unknown > 0) {
            add("$unknown ${if (unknown == 1) "day" else "days"} skipped: not synced")
        }
    }
    return lines.joinToString("\n")
}

fun formatSyncReceipt(receipt: SyncReceipt, zoneId: ZoneId, locale: Locale): String {
    if (receipt.records.isEmpty()) return "No daily step totals were sent"
    val dateFormatter = DateTimeFormatter.ofPattern("d MMM uuuu", locale)
    val numberFormatter = NumberFormat.getIntegerInstance(locale)
    val rows = receipt.records.sortedByDescending { it.date }.joinToString("\n") { record ->
        val date = runCatching { LocalDate.parse(record.date).format(dateFormatter) }
            .getOrDefault(record.date)
        val status = formatRecordStatus(record.status, record.reason)
        "$date · ${numberFormatter.format(record.steps)} steps · $status"
    }
    val summary = buildString {
        val acceptedUnit = if (receipt.processed == 1) "day" else "days"
        append("${receipt.processed} $acceptedUnit accepted")
        if (receipt.skipped > 0) {
            val skippedUnit = if (receipt.skipped == 1) "day" else "days"
            append(" · ${receipt.skipped} $skippedUnit skipped")
        }
        formatLastSync(receipt.acknowledgedAt, zoneId, locale)?.let { append(" · $it") }
    }
    val skipDetails = formatSkippedSummary(receipt.records)
    return listOfNotNull(summary, skipDetails, rows).joinToString("\n")
}

class MainActivity : ComponentActivity() {
    private val health by lazy { HealthConnectDataSource(applicationContext) }
    private val coordinator by lazy { SyncCoordinator(applicationContext) }

    private lateinit var rootView: View
    private lateinit var syncButton: MaterialButton
    private lateinit var syncProgress: LinearProgressIndicator
    private lateinit var statusText: TextView
    private lateinit var connectionStateText: TextView
    private lateinit var lastSyncText: TextView
    private lateinit var syncReceiptText: TextView
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
        connectionStateText = findViewById(R.id.text_connection_state)
        lastSyncText = findViewById(R.id.text_last_sync)
        syncReceiptText = findViewById(R.id.text_sync_receipt)
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
        lifecycleScope.launch {
            coordinator.receiptUpdates().collect { receipt ->
                syncReceiptText.text = receipt?.let {
                    formatSyncReceipt(it, ZoneId.systemDefault(), Locale.ENGLISH)
                } ?: getString(R.string.sync_receipt_never)
            }
        }

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
            connectionStateText.text = formatConnectionState(paired)
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
