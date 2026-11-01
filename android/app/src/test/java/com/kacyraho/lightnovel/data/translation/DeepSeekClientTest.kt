package com.kacyraho.lightnovel.data.translation

import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeepSeekClientTest {
    @Test
    fun parsesSuccessfulCompletionAndUsage() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """
                {"choices":[{"message":{"role":"assistant","content":"1. 你好"},"finish_reason":"stop"}],
                 "usage":{"prompt_tokens":12,"completion_tokens":34},
                 "model":"deepseek-flash"}
                """.trimIndent(),
            ),
        )
        server.start()
        try {
            val client = DeepSeekClient(server.url("/").toString(), "key")
            val result = client.complete(
                messages = listOf(ChatMessage("user", "1. こんにちは")),
                model = "deepseek-flash",
            )
            assertEquals("1. 你好", result.content)
            assertEquals(12, result.tokensIn)
            assertEquals(34, result.tokensOut)
            assertEquals("deepseek-flash", result.model)
            assertEquals("/chat/completions", server.takeRequest().path)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun allowsBlankKeyAndNormalizesV1Endpoint() = runTest {
        val server = MockWebServer()
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"choices":[{"message":{"role":"assistant","content":"1. 你好"},"finish_reason":"stop"}]}""",
            ),
        )
        server.start()
        try {
            val client = DeepSeekClient(server.url("/v1").toString(), "")
            client.complete(listOf(ChatMessage("user", "1. こんにちは")), "local-model")
            val request = server.takeRequest()
            assertEquals("/v1/chat/completions", request.path)
            assertEquals(null, request.getHeader("Authorization"))
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun marks401NonRetryableAnd429Retryable() = runTest {
        val server = MockWebServer()
        server.start()
        try {
            val client = DeepSeekClient(server.url("/").toString(), "key")

            server.enqueue(MockResponse().setResponseCode(401).setBody("unauthorized"))
            val auth = runCatching {
                client.complete(listOf(ChatMessage("user", "x")), "deepseek-flash")
            }.exceptionOrNull() as TranslationException
            assertEquals(401, auth.statusCode)
            assertFalse(auth.retryable)

            server.enqueue(MockResponse().setResponseCode(429).setBody("rate limited"))
            val rate = runCatching {
                client.complete(listOf(ChatMessage("user", "x")), "deepseek-flash")
            }.exceptionOrNull() as TranslationException
            assertEquals(429, rate.statusCode)
            assertTrue(rate.retryable)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun rejectsMalformedOrEmptyChoices() = runTest {
        val server = MockWebServer()
        server.start()
        try {
            val client = DeepSeekClient(server.url("/").toString(), "key")
            server.enqueue(MockResponse().setResponseCode(200).setBody("not-json"))
            val malformed = runCatching {
                client.complete(listOf(ChatMessage("user", "x")), "deepseek-flash")
            }.exceptionOrNull() as TranslationException
            assertTrue(malformed.retryable)

            server.enqueue(MockResponse().setResponseCode(200).setBody("""{"choices":[]}"""))
            val empty = runCatching {
                client.complete(listOf(ChatMessage("user", "x")), "deepseek-flash")
            }.exceptionOrNull() as TranslationException
            assertTrue(empty.retryable)
        } finally {
            server.shutdown()
        }
    }
}
