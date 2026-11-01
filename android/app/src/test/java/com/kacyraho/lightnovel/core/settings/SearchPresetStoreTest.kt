package com.kacyraho.lightnovel.core.settings

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class SearchPresetStoreTest {
    @Test
    fun savesDeduplicatesAndRemovesPresets() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("lightnovel_search_presets", Context.MODE_PRIVATE)
            .edit().clear().commit()
        val store = SearchPresetStore(context)

        store.save(SearchPreset(query = "百合", status = "running"))
        store.save(SearchPreset(query = "转生", characters = "long"))
        val saved = store.save(SearchPreset(query = "百合", status = "running"))

        assertEquals(2, saved.size)
        assertEquals("百合", saved.first().query)
        assertEquals(1, store.remove(saved.first().id).size)
    }
}
