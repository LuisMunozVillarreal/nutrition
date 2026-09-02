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
./gradlew test
./gradlew assembleDebug
```

El APK de depuración queda en `app/build/outputs/apk/debug/app-debug.apk`.

## Configurar Garmin, Samsung Health y Health Connect

1. Abre Samsung Health.
2. Entra en **Ajustes > Health Connect**.
3. Permite que Samsung Health escriba **Pasos**.
4. Abre esta aplicación y pulsa **Abrir ajustes de Health Connect** para confirmar que hay datos de pasos y que la app puede leerlos.
5. Pulsa **Conceder lectura de pasos**.
6. Si el dispositivo ofrece la función, concede de forma opcional **sincronización en segundo plano**.

Para las actividades Garmin:

1. Abre Garmin Connect y entra en **Más > Configuración > Health Connect**.
2. Activa la conexión y permite escribir **Ejercicio**, **Calorías activas** y **Distancia**.
3. En Health Connect comprueba que Garmin Connect aparece como origen autorizado.
4. En esta aplicación concede la lectura de pasos y actividades.

La aplicación importa únicamente sesiones cuyo origen es el paquete oficial de Garmin Connect. Para cada sesión compatible obtiene el inicio, fin, calorías activas y distancia del mismo origen. Las sesiones sin calorías activas o cuyo tipo no se puede representar como `walk`, `run`, `cycle` o `gym` se omiten en vez de inventar valores.

Si los pasos no aparecen, actualiza Samsung Health y Health Connect, vuelve a comprobar los permisos y espera a que Samsung Health publique sus datos en Health Connect. Esta app no accede directamente al SDK privado de Samsung Health: Samsung Health es la fuente y Health Connect es la capa interoperable.

## Vinculación

La pantalla solicita:

- URL base HTTPS, sin `/api`, rutas, consulta, fragmento ni credenciales. Ejemplo reservado: `https://example.com`.
- Código numérico de vinculación de 12 dígitos y un solo uso.
- Nombre del dispositivo.

Contrato de red:

- `POST {base}/api/health-sync/pair/`
  - JSON: `{"code":"…","device_name":"…"}`
  - Respuesta: `{"token":"…"}`; se ignoran metadatos adicionales.
- `POST {base}/api/health-sync/steps/`
  - Cabecera: `Authorization: Bearer ${DEVICE_TOKEN}`
  - JSON: `{"records":[{"date":"YYYY-MM-DD","steps":1234,"observed_at":"ISO-8601"}]}`
- `POST {base}/api/health-sync/activities/`
  - Cabecera: `Authorization: Bearer ${DEVICE_TOKEN}`
  - JSON: `{"records":[{"source_record_id":"…","source_modified_at":"ISO-8601","start_time":"ISO-8601","end_time":"ISO-8601","type":"run","active_kcals":420,"distance_km":7.25}]}`

No existe un hostname de despliegue integrado. La URL se introduce en tiempo de ejecución y se exige HTTPS; el manifiesto bloquea tráfico HTTP en texto claro.

## Sincronización

- **Manual:** lee los últimos 30 días disponibles. Los pasos se agrupan por día local. Las sesiones Garmin se leen individualmente y sus calorías activas y distancia se agregan dentro del intervalo de la sesión y únicamente para el mismo origen Garmin. Si no hay datos reales, no se realiza una petición de subida.
- **Periódica:** WorkManager ejecuta cada 12 horas y exige conectividad. Solo se programa si existen vinculación, todos los permisos obligatorios de lectura, soporte de la función de lectura en segundo plano y el permiso opcional `READ_HEALTH_DATA_IN_BACKGROUND`. Si falta alguno, el trabajo único se cancela.

La aplicación filtra cada agregación al origen de la propia sesión Garmin, por lo que no mezcla copias procedentes de Strava o Samsung Health. No suma registros crudos manualmente.

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

Eliminar la vinculación en el teléfono borra el token local, pero no revoca su
registro en el servidor. Para una revocación completa, usa también
**Disconnect** en la página de pasos de la aplicación web.

Para publicación en Google Play, declara exactamente estos usos de datos y permisos en **Data safety** y en el formulario de acceso a Health Connect. La actividad de justificación atiende tanto `androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE` (Android 13) como `android.intent.action.VIEW_PERMISSION_USAGE` con la categoría `HEALTH_PERMISSIONS` (Android 14 o posterior).
