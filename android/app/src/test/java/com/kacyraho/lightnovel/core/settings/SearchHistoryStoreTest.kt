package com.kacyraho.lightnovel.core.settings

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class SearchHistoryStoreTest {
    @Test
    fun remembersUniqueQueriesNewestFirst() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("lightnovel_search_history", Context.MODE_PRIVATE)
            .edit().clear().commit()
        val store = SearchHistoryStore(context)

        store.remember("转生")
        store.remember("百合")
        val history = store.remember("转生")

        assertEquals(listOf("转生", "百合"), history)
        assertEquals(history, store.load())
    }

    @Test
    fun clearRemovesHistory() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val store = SearchHistoryStore(context)
        store.remember("测试")
        store.clear()
        assertTrue(store.load().isEmpty())
    }
}
