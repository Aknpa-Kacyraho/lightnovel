package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ChapterCost
import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.ChapterTokens
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.glossary.GlossaryStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.first

class TranslationService(
    private val contentStore: ContentStore,
    private val dao: LibraryDao,
    private val settingsStore: SettingsStore,
    private val apiKeyStore: ApiKeyStore,
    private val glossaryStore: GlossaryStore? = null,
    private val versionStore: TranslationVersionStore? = null,
    private val translationStore: TranslationStore = FileTranslationStore(contentStore),
    private val clientFactory: (String, String) -> TranslationClient = { baseUrl, key ->
        DeepSeekClient(baseUrl, key)
    },
) {
    suspend fun translate(
        book: BookEntity,
        chapterIndex: Int,
        onProgress: (done: Int, total: Int) -> Unit = { _, _ -> },
    ): TranslationOutcome {
        val raw = contentStore.readRaw(book.storageDir, chapterIndex)
            ?: return TranslationOutcome.Failed("这一章没有原文文件", false)
        if (raw.isBlank()) {
            return TranslationOutcome.Failed("这一章原文为空", false)
        }
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) {
            return TranslationOutcome.Failed("未配置翻译 API Key", false)
        }
        val glossary = glossaryStore?.load()
        val config = settings.toTranslationConfig(
            glossary = glossary?.entries.orEmpty(),
            glossaryRevision = glossary?.revision.orEmpty(),
        )
        dao.updateChapterTranslation(
            bookId = book.id,
            idx = chapterIndex,
            status = "translating",
            model = settings.deepSeekModel,
            tokenIn = 0,
            tokenOut = 0,
            updatedAt = java.time.Instant.now().toString(),
        )
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val translator = ChapterTranslator(client, translationStore)
        val outcome = try {
            translator.translate(
                storageDir = book.storageDir,
                chapterIndex = chapterIndex,
                sourceText = raw,
                config = config,
                onProgress = onProgress,
            )
        } catch (error: CancellationException) {
            withContext(NonCancellable) {
                markCancelled(book, chapterIndex)
            }
            throw error
        }
        return when (outcome) {
            is TranslationOutcome.Complete -> commit(book, chapterIndex, outcome)
            is TranslationOutcome.Partial -> commit(book, chapterIndex, outcome)
            is TranslationOutcome.Failed -> {
                dao.updateChapterTranslation(
                    bookId = book.id,
                    idx = chapterIndex,
                    status = "failed",
                    model = settings.deepSeekModel,
                    tokenIn = 0,
                    tokenOut = 0,
                    updatedAt = java.time.Instant.now().toString(),
                )
                outcome
            }
        }
    }

    suspend fun markCancelled(book: BookEntity, chapterIndex: Int) {
        val zh = contentStore.readZh(book.storageDir, chapterIndex)
        val sidecar = runCatching {
            contentStore.readSidecar(book.storageDir, chapterIndex)
        }.getOrNull()
        val status = when {
            sidecar?.status == "partial" -> "partial"
            zh != null -> "complete"
            else -> "raw"
        }
        dao.updateChapterTranslation(
            bookId = book.id,
            idx = chapterIndex,
            status = status,
            model = sidecar?.modelId ?: "cancelled",
            tokenIn = sidecar?.tokens?.input ?: 0,
            tokenOut = sidecar?.tokens?.output ?: 0,
            updatedAt = java.time.Instant.now().toString(),
        )
    }

    suspend fun retranslateParagraph(
        book: BookEntity,
        chapterIndex: Int,
        paragraphIndex: Int,
    ): TranslationOutcome {
        val raw = contentStore.readRaw(book.storageDir, chapterIndex)
            ?: return TranslationOutcome.Failed("这一章没有原文文件", false)
        val zh = contentStore.readZh(book.storageDir, chapterIndex)
            ?: return TranslationOutcome.Failed("这一章还没有译文", false)
        val rawParagraphs = raw.replace("\r\n", "\n").split("\n\n")
        val zhParagraphs = zh.replace("\r\n", "\n").split("\n\n")
        val source = rawParagraphs.getOrNull(paragraphIndex)
            ?: return TranslationOutcome.Failed("找不到第 ${paragraphIndex + 1} 段原文", false)
        if (paragraphIndex !in zhParagraphs.indices) {
            return TranslationOutcome.Failed("找不到第 ${paragraphIndex + 1} 段译文", false)
        }
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) {
            return TranslationOutcome.Failed("未配置翻译 API Key", false)
        }
        val glossary = glossaryStore?.load()
        val config = settings.toTranslationConfig(
            glossary = glossary?.entries.orEmpty(),
            glossaryRevision = glossary?.revision.orEmpty(),
        )
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val translator = ChapterTranslator(client, translationStore)
        val result = translator.translateOne(source, config)
            ?: return TranslationOutcome.Failed("单段翻译失败", true)
        val old = runCatching {
            contentStore.readSidecar(book.storageDir, chapterIndex)
        }.getOrNull()
            ?: return TranslationOutcome.Failed("缺少章节翻译信息，无法安全写回", false)
        val newParagraphs = zhParagraphs.toMutableList().apply {
            this[paragraphIndex] = result.text
        }
        val newText = newParagraphs.joinToString("\n\n")
        val tokens = ChapterTokens(
            input = old.tokens.input + result.tokensIn,
            output = old.tokens.output + result.tokensOut,
        )
        val incomplete = old.incompleteParagraphs.filterNot { it == paragraphIndex }
        val cost = tokens.input / 1_000_000.0 * config.priceInCnyPerMillion +
            tokens.output / 1_000_000.0 * config.priceOutCnyPerMillion
        val sidecar = old.copy(
            status = if (incomplete.isEmpty()) "complete" else "partial",
            contentSha256 = Hashes.sha256(newText),
            translatedAt = java.time.Instant.now().toString(),
            tokens = tokens,
            cost = ChapterCost(cost, "CNY", estimated = true),
            incompleteParagraphs = incomplete,
            incompleteReason = if (incomplete.isEmpty()) null else old.incompleteReason,
            glossaryRevision = config.glossaryRevision.takeIf { it.isNotBlank() },
        )
        return commit(book, chapterIndex, TranslationOutcome.Complete(newText, sidecar))
    }

    private suspend fun commit(
        book: BookEntity,
        chapterIndex: Int,
        outcome: TranslationOutcome,
    ): TranslationOutcome {
        val text = when (outcome) {
            is TranslationOutcome.Complete -> outcome.text
            is TranslationOutcome.Partial -> outcome.text
            is TranslationOutcome.Failed -> return outcome
        }
        val sidecar = when (outcome) {
            is TranslationOutcome.Complete -> outcome.sidecar
            is TranslationOutcome.Partial -> outcome.sidecar
            is TranslationOutcome.Failed -> return outcome
        }
        return try {
            val oldText = contentStore.readZh(book.storageDir, chapterIndex)
            if (oldText != null && oldText != text) {
                val oldSidecar = runCatching {
                    contentStore.readSidecar(book.storageDir, chapterIndex)
                }.getOrNull()
                if (oldSidecar != null) {
                    versionStore?.save(book.storageDir, chapterIndex, oldText, oldSidecar)
                }
            }
            contentStore.writeZhAtomic(book.storageDir, chapterIndex, text)
            contentStore.writeSidecar(book.storageDir, chapterIndex, sidecar)
            dao.updateChapterTranslation(
                bookId = book.id,
                idx = chapterIndex,
                status = sidecar.status,
                model = sidecar.modelId,
                tokenIn = sidecar.tokens.input,
                tokenOut = sidecar.tokens.output,
                updatedAt = sidecar.translatedAt,
            )
            outcome
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            withContext(NonCancellable) {
                dao.updateChapterTranslation(
                    bookId = book.id,
                    idx = chapterIndex,
                    status = "failed",
                    model = sidecar.modelId,
                    tokenIn = sidecar.tokens.input,
                    tokenOut = sidecar.tokens.output,
                    updatedAt = java.time.Instant.now().toString(),
                )
            }
            TranslationOutcome.Failed("写入失败：${error.message}", false)
        }
    }

}
