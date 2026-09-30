# Compañero Android de sincronización de pasos

Aplicación Android mínima para leer totales diarios reales de `StepsRecord` desde Health Connect y enviarlos a un servidor configurado por el usuario. No genera ni incluye datos de ejemplo en tiempo de ejecución.

## Requisitos

- Android 9 (API 28) o posterior.
- JDK 17.
- Android SDK Platform 36 y Build Tools 35.0.0.
- Health Connect Client `1.1.0` (esta versión exige `compileSdk 36` y AGP 8.9.1 o posterior).
- En Android 13: aplicación Health Connect instalada y actualizada.
- En Android 14 o posterior: módulo Health Connect del sistema actualizado.
- Samsung Health actualizado con acceso para **escribir Pasos** en Health Connect.

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

## Configurar Samsung Health y Health Connect

1. Abre Samsung Health.
2. Entra en **Ajustes > Health Connect**.
3. Permite que Samsung Health escriba **Pasos**.
4. Abre esta aplicación y pulsa **Abrir ajustes de Health Connect** para confirmar que hay datos de pasos y que la app puede leerlos.
5. Pulsa **Conceder lectura de pasos**.
6. Si el dispositivo ofrece la función, concede de forma opcional **sincronización en segundo plano**.

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
  - Cabecera: `Authorization: Bearer <token-limitado>`
  - JSON: `{"records":[{"date":"YYYY-MM-DD","steps":1234,"observed_at":"ISO-8601"}]}`

No existe un hostname de despliegue integrado. La URL se introduce en tiempo de ejecución y se exige HTTPS; el manifiesto bloquea tráfico HTTP en texto claro.

## Sincronización

- **Manual:** lee los últimos 30 días disponibles, agrupados por día de calendario local mediante `AggregateGroupByPeriodRequest`, métrica `StepsRecord.COUNT_TOTAL` y periodo de un día. Solo se suben buckets que Health Connect devuelve; si no hay totales, no se realiza una petición de subida.
- **Periódica:** WorkManager ejecuta cada 12 horas y exige conectividad. Solo se programa si existen vinculación, `READ_STEPS`, soporte de la función de lectura en segundo plano y el permiso opcional `READ_HEALTH_DATA_IN_BACKGROUND`. Si falta alguno, el trabajo único se cancela.

Health Connect se encarga de evitar el doble conteo entre fuentes al calcular la agregación. La aplicación no suma registros crudos manualmente.

## Privacidad y seguridad

La justificación visible en la app y declarada en el manifiesto cubre ambos flujos de permisos:

- `android.permission.health.READ_STEPS`: necesario exclusivamente para calcular totales diarios de pasos.
- `android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND`: opcional, necesario únicamente para WorkManager.

La aplicación:

- no solicita permisos de escritura;
- no lee rutas, nutrición, actividad ni otros tipos de salud;
- no envía eventos de pasos sin agregar;
- envía solo fecha, total diario y hora de observación;
- no registra ni muestra el token;
- cifra URL y token de vinculación con AES-GCM y una clave no exportable de Android Keystore;
- desactiva copias de seguridad de la aplicación;
- permite eliminar la vinculación local y cancelar el trabajo periódico;
- permite revocar permisos desde Health Connect.

Eliminar la vinculación en el teléfono borra el token local, pero no revoca su
registro en el servidor. Para una revocación completa, usa también
**Disconnect** en la página de pasos de la aplicación web.

Para publicación en Google Play, declara exactamente estos usos de datos y permisos en **Data safety** y en el formulario de acceso a Health Connect. La actividad de justificación atiende tanto `androidx.health.ACTION_SHOW_PERMISSIONS_RATIONALE` (Android 13) como `android.intent.action.VIEW_PERMISSION_USAGE` con la categoría `HEALTH_PERMISSIONS` (Android 14 o posterior).
