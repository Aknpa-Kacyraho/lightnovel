package com.kacyraho.lightnovel

import android.app.Application
import java.time.Instant
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class LightnovelApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        CoroutineScope(Dispatchers.IO).launch {
            container.database.libraryDao()
                .resetInterruptedTranslations(Instant.now().toString())
        }
    }
}
