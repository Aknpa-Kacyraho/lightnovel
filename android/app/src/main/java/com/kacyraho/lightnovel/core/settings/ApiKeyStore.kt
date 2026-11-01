package com.kacyraho.lightnovel.core.settings

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json

interface ApiKeyStore {
    fun load(): String?

    fun save(key: String)

    fun clear()

    fun load(scope: String): String? = load()

    fun save(scope: String, key: String) = save(key)
}

class InMemoryApiKeyStore(
    private var value: String? = null,
) : ApiKeyStore {
    override fun load(): String? = value

    override fun save(key: String) {
        value = key
    }

    override fun clear() {
        value = null
    }
}

class KeystoreApiKeyStore(
    context: Context,
) : ApiKeyStore {
    private val prefs = context.getSharedPreferences("lightnovel_secrets", Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true }
    private val mapSerializer = MapSerializer(String.serializer(), String.serializer())

    override fun load(): String? =
        loadMap()[DEFAULT_SCOPE] ?: loadLegacy()

    override fun save(key: String) = save(DEFAULT_SCOPE, key)

    override fun load(scope: String): String? {
        loadMap()[scope]?.let { return it }
        if (scope == LEGACY_SCOPE) return loadLegacy()
        return null
    }

    override fun save(scope: String, key: String) {
        val values = loadMap().toMutableMap()
        values[scope] = key
        writeEncrypted(MAP_KEY, json.encodeToString(mapSerializer, values))
    }

    override fun clear() {
        prefs.edit().remove(MAP_KEY).remove(LEGACY_KEY).apply()
    }

    private fun loadMap(): Map<String, String> {
        val raw = decrypt(MAP_KEY) ?: return emptyMap()
        return runCatching { json.decodeFromString(mapSerializer, raw) }
            .getOrDefault(emptyMap())
    }

    private fun loadLegacy(): String? = decrypt(LEGACY_KEY)

    private fun decrypt(name: String): String? {
        val encoded = prefs.getString(name, null) ?: return null
        return runCatching {
            val bytes = Base64.decode(encoded, Base64.NO_WRAP)
            if (bytes.size <= IV_SIZE) return@runCatching null
            val iv = bytes.copyOfRange(0, IV_SIZE)
            val data = bytes.copyOfRange(IV_SIZE, bytes.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
            cipher.doFinal(data).toString(Charsets.UTF_8)
        }.getOrNull()
    }

    private fun writeEncrypted(name: String, value: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val combined = cipher.iv + encrypted
        prefs.edit().putString(name, Base64.encodeToString(combined, Base64.NO_WRAP)).apply()
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "lightnovel_deepseek_key"
        const val MAP_KEY = "api_keys"
        const val LEGACY_KEY = "deepseek_key"
        const val LEGACY_SCOPE = "api.deepseek.com"
        const val DEFAULT_SCOPE = "default"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_SIZE = 12
    }
}
