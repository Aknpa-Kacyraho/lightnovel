package com.kacyraho.lightnovel.data.online

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

interface NoveliaSessionStore {
    fun load(): String?
    fun save(token: String)
    fun clear()
}

class KeystoreNoveliaSessionStore(
    context: Context,
) : NoveliaSessionStore {
    private val prefs = context.getSharedPreferences("lightnovel_secrets", Context.MODE_PRIVATE)

    override fun load(): String? {
        val encoded = prefs.getString(KEY, null) ?: return null
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

    override fun save(token: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString(KEY, Base64.encodeToString(cipher.iv + encrypted, Base64.NO_WRAP))
            .apply()
    }

    override fun clear() {
        prefs.edit().remove(KEY).apply()
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
        const val ALIAS = "lightnovel_novelia_session"
        const val KEY = "novelia_session_token"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_SIZE = 12
    }
}
