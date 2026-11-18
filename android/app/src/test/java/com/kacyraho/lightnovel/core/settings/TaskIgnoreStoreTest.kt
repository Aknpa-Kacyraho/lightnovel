package com.kacyraho.lightnovel.core.settings

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class TaskIgnoreStoreTest {
    private lateinit var context: Context
    private lateinit var store: TaskIgnoreStore

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().commit()
        store = TaskIgnoreStore(context)
    }

    @Test
    fun startsEmpty() {
        assertTrue(store.load().isEmpty())
    }

    @Test
    fun ignoresChapterAndPersists() {
        store.ignore("book-a", 3)

        val reopened = TaskIgnoreStore(context)
        assertEquals(setOf("book-a/3"), reopened.load())
    }

    @Test
    fun ignoringSameChapterTwiceKeepsOneEntry() {
        store.ignore("book-a", 3)
        store.ignore("book-a", 3)

        assertEquals(setOf("book-a/3"), store.load())
    }

    @Test
    fun clearRemovesOnlyTargetChapter() {
        store.ignore("book-a", 3)
        store.ignore("book-a", 4)
        store.ignore("book-b", 3)

        val remaining = store.clear("book-a", 3)

        assertEquals(setOf("book-a/4", "book-b/3"), remaining)
        assertEquals(setOf("book-a/4", "book-b/3"), store.load())
    }

    @Test
    fun clearOnMissingEntryIsSafe() {
        store.ignore("book-a", 3)

        assertEquals(setOf("book-a/3"), store.clear("book-c", 9))
    }

    @Test
    fun corruptSeparatorsAreIgnored() {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY, "\u001Fbook-a/1\u001F\u001Fbook-b/2\u001F")
            .commit()

        assertEquals(setOf("book-a/1", "book-b/2"), TaskIgnoreStore(context).load())
    }

    private companion object {
        const val PREFS = "lightnovel_task_ignore"
        const val KEY = "tasks"
    }
}
