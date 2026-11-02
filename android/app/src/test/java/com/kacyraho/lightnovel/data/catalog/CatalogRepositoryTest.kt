package com.kacyraho.lightnovel.data.catalog

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.source.SourceBook
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CatalogRepositoryTest {
    @Test
    fun remembersSearchResultsAndKeepsTranslations() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val repository = CatalogRepository(db.catalogDao())
            val original = SourceBook(
                provider = "kakuyomu",
                id = "123",
                title = "【所以你的封面】",
                author = "作者",
                tags = listOf("悪役令嬢", "転生"),
                episodes = 12,
                synopsis = "简介",
                updatedAt = "2026-10-01",
                status = "running",
                characters = 120_000,
            )
            assertEquals(1, repository.remember(listOf(original)))
            val first = repository.observeAll().first().single()
            assertEquals("【所以你的封面】", first.title)
            assertEquals(listOf("悪役令嬢", "転生"), BookTags.decode(first.tagsJson))
            assertEquals(
                listOf("反派千金", "转生"),
                first.tagPairs().map { it.second },
            )
            assertNotNull(first.firstSeenAt)

            repository.remember(
                listOf(
                    original.copy(
                        titleZh = "所以你的封面",
                        tagsZh = listOf("反派千金", "转生"),
                        synopsis = "",
                    ),
                ),
            )
            val merged = repository.observeAll().first().single()
            assertEquals("所以你的封面", merged.titleZh)
            assertEquals("简介", merged.synopsis)
            assertEquals(listOf("反派千金", "转生"), BookTags.decode(merged.tagsZhJson))
            assertEquals(first.firstSeenAt, merged.firstSeenAt)
        } finally {
            db.close()
        }
    }
}
