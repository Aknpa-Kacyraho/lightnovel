package com.kacyraho.lightnovel.feature.reader

import android.content.Context
import android.content.Intent
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.util.Locale

class ReaderTtsController(private val context: Context) {
    var ready by mutableStateOf(false)
        private set
    var speaking by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    private var engine: TextToSpeech? = null
    private var fallbackTried = false

    private val listener = TextToSpeech.OnInitListener { status ->
        if (status == TextToSpeech.SUCCESS) {
            ready = true
            error = null
        } else if (!fallbackTried) {
            fallbackTried = true
            val fallback = context.packageManager
                .queryIntentServices(
                    Intent("android.intent.action.TTS_SERVICE"),
                    0,
                )
                .firstOrNull()
                ?.serviceInfo
                ?.packageName
            if (fallback != null) {
                initEngine(fallback)
            } else {
                error = "系统没有可用的 TTS 语音引擎"
            }
        } else {
            error = "系统 TTS 引擎不可用"
        }
    }

    init {
        initEngine(null)
    }

    private fun initEngine(engineName: String?) {
        engine?.shutdown()
        engine = if (engineName == null) {
            TextToSpeech(context.applicationContext, listener)
        } else {
            TextToSpeech(context.applicationContext, listener, engineName)
        }
        engine?.setOnUtteranceProgressListener(
            object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {
                    speaking = true
                }

                override fun onDone(utteranceId: String?) {
                    speaking = false
                }

                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) {
                    speaking = false
                    error = "朗读失败"
                }

                override fun onError(utteranceId: String?, errorCode: Int) {
                    speaking = false
                    error = "朗读失败"
                }
            },
        )
    }

    fun speak(text: String, japanese: Boolean): Boolean {
        val tts = engine
        if (!ready || tts == null || text.isBlank()) return false
        val language = if (japanese) Locale.JAPANESE else Locale.SIMPLIFIED_CHINESE
        val result = tts.setLanguage(language)
        if (result == TextToSpeech.LANG_MISSING_DATA ||
            result == TextToSpeech.LANG_NOT_SUPPORTED
        ) {
            error = if (japanese) "TTS 引擎缺少日文语音" else "TTS 引擎缺少中文语音"
            return false
        }
        tts.setSpeechRate(1.0f)
        error = null
        speaking = true
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "lightnovel-reader")
        return true
    }

    fun stop() {
        engine?.stop()
        speaking = false
    }

    fun shutdown() {
        engine?.stop()
        engine?.shutdown()
        engine = null
    }
}
