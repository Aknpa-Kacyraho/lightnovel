package com.kacyraho.lightnovel

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.kacyraho.lightnovel.core.settings.AppSettings
import com.kacyraho.lightnovel.navigation.LightnovelNavHost
import com.kacyraho.lightnovel.ui.theme.LightnovelTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as LightnovelApp).container
        setContent {
            val settings by container.settingsStore.settings.collectAsState(
                initial = AppSettings(),
            )
            val darkTheme = when (settings.themeMode) {
                "light" -> false
                "dark" -> true
                else -> isSystemInDarkTheme()
            }
            LightnovelTheme(themeId = settings.appTheme, darkTheme = darkTheme) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    LightnovelNavHost(container)
                }
            }
        }
    }
}
