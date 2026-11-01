package com.kacyraho.lightnovel.data.online

import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class NoveliaClientTest {
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun searchParsesPageAndEncodesQuery() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """{"pageNumber":0,"items":[{"providerId":"kakuyomu","novelId":"123","titleJp":"テスト","titleZh":"测试","type":"连载中","total":3,"sakura":2}]}""",
            ),
        )
        val client = NoveliaClient(initialBaseUrl = server.url("/api/").toString())
        val page = client.search("転生")

        assertEquals(1, page.items.size)
        assertEquals("测试", page.items.single().displayTitle)
        assertEquals(3, page.items.single().total)
        val request = server.takeRequest()
        assertEquals("/api/novel", request.requestUrl?.encodedPath)
        assertEquals("転生", request.requestUrl?.queryParameter("query"))
        assertEquals("1", request.requestUrl?.queryParameter("sort"))
    }

    @Test
    fun detailAndChapterParse() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """{"titleJp":"テスト","titleZh":"测试","authors":[{"name":"作者"}],"toc":[{"titleJp":"一","chapterId":"c1"},{"titleJp":"二","chapterId":"c2"}]}""",
            ),
        )
        server.enqueue(
            MockResponse().setBody(
                """{"titleJp":"一","paragraphs":["原文一","原文二"],"sakuraParagraphs":["译文一","译文二"]}""",
            ),
        )
        val client = NoveliaClient(initialBaseUrl = server.url("/api/").toString())
        val detail = client.detail("kakuyomu", "123")
        val chapter = client.chapter("kakuyomu", "123", "c1")

        assertEquals("测试", detail.displayTitle)
        assertEquals("作者", detail.authorNames)
        assertEquals(2, detail.toc.size)
        assertEquals("译文一", chapter.bestTranslation()?.first())
        assertEquals("sakura", chapter.translationModel())
        assertTrue(server.takeRequest().path!!.startsWith("/api/novel/kakuyomu/123"))
    }
}
