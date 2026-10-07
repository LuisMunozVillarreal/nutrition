package com.nutrition.healthsync.storage

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.nutrition.healthsync.auth.PendingSignIn
import com.nutrition.healthsync.network.HealthSyncJson
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SyncReceipt(
    @SerialName("syncedAt") val acknowledgedAt: String,
    val records: List<SyncReceiptRecord>,
    val processed: Int,
    val skipped: Int,
)

@Serializable
data class SyncReceiptRecord(
    val date: String,
    val steps: Long,
    val status: String = "unknown",
    val reason: String? = null,
)

@Serializable
data class Pairing(
    val baseUrl: String,
    val token: String,
    val lastReceipt: SyncReceipt? = null,
    val refreshToken: String? = null,
    val accessExpiresAt: Long = 0,
    val pendingRefreshToken: String? = null,
)

class SecurePairingStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    @SuppressLint("ApplySharedPref", "UseKtx")
    fun save(pairing: Pairing) = synchronized(STORE_LOCK) {
        require(pairing.token.isNotBlank()) { "The token cannot be empty" }
        val cipher = Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        }
        val plaintext = HealthSyncJson.codec.encodeToString(Pairing.serializer(), pairing)
            .toByteArray(Charsets.UTF_8)
        val encrypted = cipher.doFinal(plaintext)
        check(
            preferences.edit()
                .putString(KEY_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .putString(KEY_CIPHERTEXT, Base64.encodeToString(encrypted, Base64.NO_WRAP))
                .commit(),
        ) { "Could not save the pairing" }
    }

    fun load(): Pairing? = synchronized(STORE_LOCK) {
        val snapshot = preferences.all
        val iv = snapshot[KEY_IV] as? String ?: return null
        val ciphertext = snapshot[KEY_CIPHERTEXT] as? String ?: return null
        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                init(
                    Cipher.DECRYPT_MODE,
                    getOrCreateKey(),
                    GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)),
                )
            }
            val plaintext = cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP))
                .toString(Charsets.UTF_8)
            HealthSyncJson.codec.decodeFromString(Pairing.serializer(), plaintext)
                .takeIf { it.baseUrl.isNotBlank() && it.token.isNotBlank() }
        }.getOrElse {
            // A transient Keystore failure is not evidence of lost authorization.
            null
        }
    }

    fun receiptUpdates(): Flow<SyncReceipt?> = callbackFlow {
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == KEY_IV || key == KEY_CIPHERTEXT) trySend(Unit)
        }
        preferences.registerOnSharedPreferenceChangeListener(listener)
        trySend(Unit)
        awaitClose {
            preferences.unregisterOnSharedPreferenceChangeListener(listener)
        }
    }.conflate()
        .map { load()?.lastReceipt }
        .flowOn(Dispatchers.IO)

    @SuppressLint("ApplySharedPref", "UseKtx")
    fun savePending(pending: PendingSignIn?) = synchronized(STORE_LOCK) {
        val editor = preferences.edit()
        if (pending == null) {
            editor.remove("auth_iv").remove("auth_ciphertext")
        } else {
            val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                init(Cipher.ENCRYPT_MODE, getOrCreateKey())
            }
            val plaintext = HealthSyncJson.codec.encodeToString(PendingSignIn.serializer(), pending)
            editor.putString("auth_iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            editor.putString("auth_ciphertext", Base64.encodeToString(cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP))
        }
        check(editor.commit()) { "Could not save sign-in state" }
    }

    fun pending(): PendingSignIn? = synchronized(STORE_LOCK) {
        val snapshot = preferences.all
        val iv = snapshot["auth_iv"] as? String ?: return null
        val ciphertext = snapshot["auth_ciphertext"] as? String ?: return null
        val cipher = Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
        }
        val plaintext = cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP)).toString(Charsets.UTF_8)
        HealthSyncJson.codec.decodeFromString(PendingSignIn.serializer(), plaintext)
    }

    @SuppressLint("ApplySharedPref", "UseKtx")
    fun clear() = synchronized(STORE_LOCK) {
        check(preferences.edit().clear().commit()) { "Could not remove saved sign-in" }
    }

    private fun getOrCreateKey(): SecretKey = synchronized(KEY_LOCK) {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE).run {
            init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
            generateKey()
        }
    }

    private companion object {
        val STORE_LOCK = Any()
        val KEY_LOCK = Any()
        const val PREFERENCES = "secure_health_sync_pairing"
        const val KEY_IV = "iv"
        const val KEY_CIPHERTEXT = "ciphertext"
        const val KEY_ALIAS = "nutrition_health_sync_scoped_token_v1"
        const val KEYSTORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}