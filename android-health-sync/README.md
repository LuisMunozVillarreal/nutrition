# Compañero Android de sincronización de salud

Aplicación Android para leer desde Health Connect totales diarios reales de pasos y sesiones de ejercicio originadas por Garmin Connect, y enviarlos a un servidor configurado por el usuario. No genera ni incluye datos de ejemplo en tiempo de ejecución.

## Requisitos

- Android 9 (API 28) o posterior.
- JDK 17.
- Android SDK Platform 36 y Build Tools 35.0.0.
- Health Connect Client `1.1.0` (esta versión exige `compileSdk 36` y AGP 8.9.1 o posterior).
- En Android 13: aplicación Health Connect instalada y actualizada.
- En Android 14 o posterior: módulo Health Connect del sistema actualizado.
- Samsung Health actualizado con acceso para **escribir Pasos** en Health Connect.
- Garmin Connect actualizado y Android 14 o posterior, con acceso para escribir **Ejercicio**, **Calorías activas** y **Distancia** en Health Connect.

## Compilar

Crea un `local.properties` local, sin versionarlo:

```properties
sdk.dir=/ruta/al/Android/Sdk
```

Después ejecuta:

```bash
./gradlew testProductionDebugUnitTest testSandboxDebugUnitTest
./gradlew assembleProductionDebug assembleSandboxDebug
```

The production-profile APK is written to
`app/build/outputs/apk/production/debug/app-production-debug.apk`. It keeps the
existing `com.nutrition.healthsync` identity, so installing an update preserves
the encrypted production pairing and configuration.

The sandbox APK is written to
`app/build/outputs/apk/sandbox/debug/app-sandbox-debug.apk`. It installs beside
the production profile as **Nutrition Test** with the isolated
`com.nutrition.healthsync.testing` identity. Use it for preview or staging
servers so production configuration and scheduled sync remain untouched.

## Configurar Garmin, Samsung Health y Health Connect

1. Abre Samsung Health.
2. Entra en **Ajustes > Health Connect**.
3. Permite que Samsung Health escriba **Pasos**.
4. Abre esta aplicación y pulsa **Abrir ajustes de Health Connect** para confirmar que hay datos de pasos y que la app puede leerlos.
5. Pulsa **Conceder lectura de pasos y actividades**. Si solo concedes pasos, la sincronización de pasos seguirá funcionando sin exigir los permisos de actividad.
6. Si el dispositivo ofrece la función, concede de forma opcional **sincronización en segundo plano**.

Para las actividades Garmin:

1. Abre Garmin Connect y entra en **Más > Configuración > Health Connect**.
2. Activa la conexión y permite escribir **Ejercicio**, **Calorías activas** y **Distancia**.
3. En Health Connect comprueba que Garmin Connect aparece como origen autorizado.
4. En esta aplicación concede la lectura de pasos y actividades.

La aplicación importa únicamente sesiones cuyo origen es el paquete oficial de Garmin Connect. Para cada sesión compatible obtiene el inicio, fin, calorías activas y distancia del mismo origen. Las sesiones sin calorías activas o cuyo tipo no se puede representar como `walk`, `run`, `cycle` o `gym` se omiten en vez de inventar valores.

Si los pasos no aparecen, actualiza Samsung Health y Health Connect, vuelve a comprobar los permisos y espera a que Samsung Health publique sus datos en Health Connect. Esta app no accede directamente al SDK privado de Samsung Health: Samsung Health es la fuente y Health Connect es la capa interoperable.

## Browser sign-in

Enter the HTTPS server address and device name in Settings, then select **Sign in with Nutrition**. The server address must not contain `/api`, paths, a query, a fragment, or credentials. Reserved example: `https://example.com`.

The account card shows **Connected** in green for readable saved credentials that have not been rejected by the server. **Sign in again** replaces the initial sign-in action when a saved connection exists, including when it needs attention. The status is restored from encrypted storage and follows credential changes while Settings is open. Starting or cancelling browser sign-in does not mark the device connected. **Disconnected** means there is no saved connection or the server has rejected its credentials; an unreadable saved credential shows **Unavailable** without deleting it. Connected describes the saved account connection, not current network reachability. Remote revocation becomes visible when the next sync or renewal detects it.

The system browser opens the Nutrition login page and then asks for explicit consent to upload daily step totals. It returns a single-use, five-minute code to this app. PKCE S256, a random state, the exact callback URI and the server origin bind the response to the initiating app. The app never receives the account password. Cancel in the browser consent page to decline access.

The app keeps pending sign-in state and credentials encrypted with Android Keystore, outside backups. Access tokens last 15 minutes. Before sync, the app silently rotates its narrowly scoped renewal credential. Renewal extends the device lifetime to 180 days from that renewal. A replacement is committed locally before the request; a lost response or failed final save can retry that exact replacement, including after process recreation. Sync, renewal and disconnect share a process-wide mutex. A lost initial code-exchange response requires starting sign-in again because authorization codes are single-use.

The production and sandbox apps use different callback schemes and separate encrypted storage. Existing manual-pairing credentials continue to sync without renewal; reconnect through browser sign-in to obtain renewable credentials. The legacy pairing endpoint remains available for older clients.

Network contract:

- `POST {base}/api/health-sync/authorize/`: explicit browser consent, account bearer authentication, matching Origin and S256 challenge.
- `POST {base}/api/health-sync/token/`: code plus PKCE verifier, or renewal credential plus a durable replacement. Credentials are sent only in POST bodies.
- `POST {base}/api/health-sync/revoke/`: revoke this device's access and renewal credentials.
- `POST {base}/api/health-sync/steps/`
  - Cabecera: `Authorization: Bearer ${DEVICE_TOKEN}`
  - JSON: `{"records":[{"date":"YYYY-MM-DD","steps":1234,"observed_at":"ISO-8601"}]}`
- `POST {base}/api/health-sync/activities/`
  - Cabecera: `Authorization: Bearer ${DEVICE_TOKEN}`
  - JSON: `{"records":[{"source_record_id":"…","source_modified_at":"ISO-8601","start_time":"ISO-8601","end_time":"ISO-8601","type":"run","active_kcals":420,"distance_km":7.25}]}`

No existe un hostname de despliegue integrado. La URL se introduce en tiempo de ejecución y se exige HTTPS; el manifiesto bloquea tráfico HTTP en texto claro.

## Sincronización

- **Manual:** lee los últimos 30 días disponibles. Los pasos se agrupan por día local. Las sesiones Garmin se leen individualmente y sus calorías activas y distancia se agregan dentro del intervalo de la sesión y únicamente para el mismo origen Garmin. Si no hay datos reales, no se realiza una petición de subida.
- **Periódica:** WorkManager ejecuta cada 12 horas y exige conectividad. Solo se programa si existen vinculación, soporte de lectura en segundo plano, el permiso opcional `READ_HEALTH_DATA_IN_BACKGROUND` y al menos un flujo legible: pasos, o el grupo completo de permisos de actividad. Si falta alguno de esos requisitos, el trabajo único se cancela.

La aplicación filtra cada agregación al origen de la propia sesión Garmin, por lo que no mezcla copias procedentes de Strava o Samsung Health. No suma registros crudos manualmente. Para evitar atribuir las mismas calorías o distancia dos veces cuando Garmin presenta intervalos solapados, conserva un conjunto cronológico no solapado; también omite sesiones que excedan los límites admitidos por el servidor.

## Privacidad y seguridad

La justificación visible en la app y declarada en el manifiesto cubre ambos flujos de permisos:

- `android.permission.health.READ_STEPS`: necesario para calcular totales diarios de pasos.
- `android.permission.health.READ_EXERCISE`: necesario para identificar sesiones Garmin, su tipo e intervalo.
- `android.permission.health.READ_ACTIVE_CALORIES_BURNED`: necesario para importar el gasto activo de cada sesión, sin BMR.
- `android.permission.health.READ_DISTANCE`: necesario para importar la distancia de cada sesión cuando exista.
- `android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND`: opcional, necesario únicamente para WorkManager.

La aplicación:

- no solicita permisos de escritura;
- no lee rutas, nutrición, frecuencia cardiaca ni calorías basales;
- no envía eventos de pasos sin agregar;
- envía totales diarios de pasos y, para sesiones Garmin, identificador, modificación, intervalo, tipo, calorías activas y distancia;
- no registra ni muestra el token;
- cifra URL y token de vinculación con AES-GCM y una clave no exportable de Android Keystore;
- desactiva copias de seguridad de la aplicación;
- permite eliminar la vinculación local y cancelar el trabajo periódico;
- permite revocar permisos desde Health Connect.

For browser-connected devices, **Disconnect account** revokes both server credentials before clearing local data and cancelling periodic sync. It requires connectivity. You can also revoke the individual phone from **Devices** on the Nutrition website. Legacy manual-pairing credentials can only be removed locally by the phone; revoke their server record in **Devices** as well.

Para publicación en Google Play, declara exactamente estos usos de datos y permisos en **Data safety** y en el formulario de acceso a Health Connect. La actividad de justificación atiende tanto `androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE` (Android 13) como `android.intent.action.VIEW_PERMISSION_USAGE` con la categoría `HEALTH_PERMISSIONS` (Android 14 o posterior).
