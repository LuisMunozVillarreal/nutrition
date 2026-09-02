package com.nutrition.healthsync

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.text.InputFilter
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.core.net.toUri
import androidx.lifecycle.lifecycleScope
import com.nutrition.healthsync.health.HealthConnectDataSource
import com.nutrition.healthsync.sync.PeriodicSyncScheduler
import com.nutrition.healthsync.sync.SyncCoordinator
import kotlinx.coroutines.launch

@SuppressLint("SetTextI18n") // This private companion currently ships in Spanish only.
class MainActivity : ComponentActivity() {
    private val health by lazy { HealthConnectDataSource(applicationContext) }
    private val coordinator by lazy { SyncCoordinator(applicationContext) }

    private lateinit var endpointInput: EditText
    private lateinit var codeInput: EditText
    private lateinit var deviceNameInput: EditText
    private lateinit var healthSettingsButton: Button
    private lateinit var stepsPermissionButton: Button
    private lateinit var backgroundPermissionButton: Button
    private lateinit var pairButton: Button
    private lateinit var syncButton: Button
    private lateinit var unpairButton: Button
    private lateinit var statusText: TextView

    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract(),
    ) { granted ->
        val message = if (granted.containsAll(HealthConnectDataSource.REQUIRED_READ_PERMISSIONS)) {
            "Permisos de pasos y actividades concedidos."
        } else {
            "No se concedieron todos los permisos. Puedes volver a intentarlo."
        }
        refreshState(message)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildInterface()
        coordinator.pairing()?.let { endpointInput.setText(it.baseUrl) }
        if (intent.action == ACTION_SHOW_PERMISSIONS_RATIONALE) {
            statusText.text = "Revisa cómo y por qué se usan los pasos y las actividades antes de conceder acceso."
        }
    }

    override fun onResume() {
        super.onResume()
        refreshState()
    }

    private fun buildInterface() {
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(20), dp(20), dp(32))
        }

        content.addView(text("Sincronización de salud", 26f, bold = true))
        content.addView(
            text(
                "Lee pasos y actividades de Garmin desde Health Connect y los envía al servidor que tú indiques.",
                16f,
            ),
        )

        content.addView(section("1. Garmin, Samsung Health y Health Connect"))
        content.addView(
            text(
                "En Garmin Connect abre Más > Configuración > Health Connect y permite escribir Ejercicio, " +
                    "Calorías activas y Distancia. Garmin requiere Android 14 o posterior para esta conexión. " +
                    "Para pasos de Samsung, permite también que Samsung Health escriba Pasos. Comprueba ambos " +
                    "orígenes en los ajustes de Health Connect.",
                15f,
            ),
        )
        healthSettingsButton = button("Abrir ajustes de Health Connect") { openHealthConnect() }
        content.addView(healthSettingsButton)

        stepsPermissionButton = button("Conceder lectura de pasos y actividades") {
            requestPermissions(HealthConnectDataSource.REQUIRED_READ_PERMISSIONS)
        }
        content.addView(stepsPermissionButton)

        backgroundPermissionButton = button("Permitir sincronización en segundo plano") {
            lifecycleScope.launch {
                if (health.supportsBackgroundRead()) {
                    requestPermissions(
                        HealthConnectDataSource.REQUIRED_READ_PERMISSIONS +
                            HealthConnectDataSource.READ_IN_BACKGROUND,
                    )
                } else {
                    statusText.text = "Este dispositivo no ofrece lectura de Health Connect en segundo plano."
                }
            }
        }
        content.addView(backgroundPermissionButton)

        content.addView(section("2. Vincular con tu servidor"))
        content.addView(text("URL base HTTPS (sin /api ni otras rutas)", 14f, bold = true))
        endpointInput = input("https://example.com").apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        content.addView(endpointInput)
        content.addView(text("Código de vinculación", 14f, bold = true))
        codeInput = input("12 dígitos").apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(InputFilter.LengthFilter(PAIRING_CODE_DIGITS))
        }
        content.addView(codeInput)
        content.addView(text("Nombre del dispositivo", 14f, bold = true))
        deviceNameInput = input("Mi teléfono").apply {
            setText(listOf(Build.MANUFACTURER, Build.MODEL).joinToString(" ").trim())
        }
        content.addView(deviceNameInput)
        pairButton = button("Vincular") { pairDevice() }
        content.addView(pairButton)

        content.addView(section("3. Sincronizar"))
        syncButton = button("Sincronizar ahora") { manualSync() }
        content.addView(syncButton)
        unpairButton = button("Eliminar vinculación local") {
            coordinator.clearPairing()
            PeriodicSyncScheduler.cancel(this)
            codeInput.text.clear()
            refreshState("Vinculación eliminada.")
        }
        content.addView(unpairButton)

        statusText = text("Comprobando estado…", 15f).apply {
            setPadding(0, dp(12), 0, dp(12))
            setTextIsSelectable(true)
        }
        content.addView(statusText)

        content.addView(section("Privacidad y permisos"))
        content.addView(
            text(
                "La app lee totales diarios de pasos y, exclusivamente para sesiones originadas por Garmin Connect, " +
                    "el tipo de ejercicio, inicio, fin, calorías activas y distancia. No lee rutas, nutrición, " +
                    "frecuencia cardiaca ni calorías basales. Envía los pasos agregados y los campos de ejercicio " +
                    "indicados al servidor configurado. El permiso de segundo plano es opcional y solo se usa " +
                    "para WorkManager. El token limitado de vinculación se cifra con una clave AES-GCM no exportable " +
                    "del Android Keystore. Puedes revocar permisos en Health Connect y eliminar la vinculación aquí.",
                14f,
            ),
        )

        setContentView(ScrollView(this).apply { addView(content) })
    }

    private fun refreshState(message: String? = null) {
        lifecycleScope.launch {
            val availability = health.availability()
            val available = availability == HealthConnectClient.SDK_AVAILABLE
            val permissions = if (available) health.grantedPermissions() else emptySet()
            val paired = coordinator.pairing() != null
            val supportsBackground = available && health.supportsBackgroundRead()
            val hasRequiredReads = permissions.containsAll(HealthConnectDataSource.REQUIRED_READ_PERMISSIONS)
            val hasBackground = HealthConnectDataSource.READ_IN_BACKGROUND in permissions

            healthSettingsButton.isEnabled = true
            stepsPermissionButton.isEnabled = available && !hasRequiredReads
            backgroundPermissionButton.isEnabled = supportsBackground && !hasBackground
            backgroundPermissionButton.visibility = if (supportsBackground) View.VISIBLE else View.GONE
            pairButton.isEnabled = true
            syncButton.isEnabled = available && hasRequiredReads && paired
            unpairButton.isEnabled = paired

            val healthStatus = when (availability) {
                HealthConnectClient.SDK_AVAILABLE -> "Health Connect disponible"
                HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> "Health Connect necesita actualizarse"
                else -> "Health Connect no está disponible"
            }
            val backgroundStatus = when {
                !supportsBackground -> "segundo plano no disponible"
                hasBackground -> "segundo plano concedido"
                else -> "segundo plano opcional no concedido"
            }
            val pairingStatus = if (paired) "dispositivo vinculado" else "sin vincular"
            val lastSync = coordinator.lastSync()?.let { "; última sincronización: $it" }.orEmpty()
            statusText.text = message ?: (
                "$healthStatus; datos: ${if (hasRequiredReads) "permitidos" else "faltan permisos"}; " +
                    "$backgroundStatus; $pairingStatus$lastSync."
                )

            PeriodicSyncScheduler.reconcile(this@MainActivity)
        }
    }

    private fun pairDevice() {
        lifecycleScope.launch {
            setBusy(true)
            var message = "No se pudo vincular el dispositivo."
            runCatching {
                coordinator.pair(
                    endpointInput.text.toString(),
                    codeInput.text.toString(),
                    deviceNameInput.text.toString(),
                )
            }.onSuccess {
                codeInput.text.clear()
                message = "Dispositivo vinculado. El token se guardó cifrado."
                PeriodicSyncScheduler.reconcile(this@MainActivity)
            }.onFailure { error ->
                message = error.message ?: message
            }
            setBusy(false)
            refreshState(message)
        }
    }

    private fun manualSync() {
        lifecycleScope.launch {
            setBusy(true)
            var message = "No se pudo completar la sincronización."
            runCatching { coordinator.syncNow() }
                .onSuccess { result ->
                    message = if (result.recordsProcessed == 0 && result.recordsSkipped == 0) {
                        "Health Connect no devolvió pasos ni actividades Garmin para los últimos 30 días; no se envió nada."
                    } else {
                        "Sincronización completada: ${result.recordsProcessed} registros procesados" +
                            if (result.recordsSkipped > 0) ", ${result.recordsSkipped} omitidos." else "."
                    }
                }
                .onFailure { error ->
                    message = error.message ?: message
                }
            setBusy(false)
            refreshState(message)
        }
    }

    private fun requestPermissions(permissions: Set<String>) {
        if (health.isAvailable()) permissionLauncher.launch(permissions)
        else statusText.text = "Health Connect no está disponible."
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
            statusText.text = "No se encontró una pantalla de Health Connect en este dispositivo."
        }
    }

    private fun setBusy(busy: Boolean) {
        pairButton.isEnabled = !busy
        syncButton.isEnabled = !busy
        stepsPermissionButton.isEnabled = !busy
        backgroundPermissionButton.isEnabled = !busy
        unpairButton.isEnabled = !busy && coordinator.pairing() != null
    }

    private fun section(value: String): TextView = text(value, 20f, bold = true).apply {
        setPadding(0, dp(22), 0, dp(8))
    }

    private fun text(value: String, size: Float, bold: Boolean = false): TextView = TextView(this).apply {
        text = value
        textSize = size
        if (bold) setTypeface(typeface, Typeface.BOLD)
        setLineSpacing(0f, 1.1f)
    }

    private fun input(hintValue: String): EditText = EditText(this).apply {
        hint = hintValue
        setSingleLine(true)
        importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
    }

    private fun button(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        isAllCaps = false
        setOnClickListener { action() }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private companion object {
        const val ACTION_SHOW_PERMISSIONS_RATIONALE = "androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE"
        const val HEALTH_CONNECT_PACKAGE = "com.google.android.apps.healthdata"
        const val PAIRING_CODE_DIGITS = 12
    }
}