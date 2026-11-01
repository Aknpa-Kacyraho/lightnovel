package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.FileContentStore
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class TranslationVersionStoreTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun keepsLatestOldVersionAndComputesParagraphDiff() {
        val store = TranslationVersionStore(
            FileContentStore(tmp.newFolder("data").toPath()),
        )
        val sidecar = ChapterSidecar(
            status = "complete",
            sourceSha256 = "source",
            contentSha256 = "content",
            translationConfigHash = "config",
            modelProvider = "test",
            modelId = "model",
            promptVersion = "v1",
            translatedAt = Instant.now().toString(),
        )
        store.save("book", 1, "第一段\n\n第二段", sidecar)
        Thread.sleep(3)
        store.save("book", 1, "第一段\n\n旧译文", sidecar)

        val latest = store.latest("book", 1)
        assertNotNull(latest)
        assertEquals("旧译文", latest!!.text.split("\n\n")[1])
        assertEquals(1, store.diffParagraphs("第一段\n\n第二段", "第一段\n\n新译文"))
    }
}
