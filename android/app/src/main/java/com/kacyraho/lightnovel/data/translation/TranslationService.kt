package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ChapterCost
import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.ChapterTokens
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.core.text.Paragraphs
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.data.story.StoryMemoryStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.first

class TranslationService(
    private val contentStore: ContentStore,
    private val dao: LibraryDao,
    private val settingsStore: SettingsStore,
    private val apiKeyStore: ApiKeyStore,
    private val storyMemoryStore: StoryMemoryStore? = null,
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
        val memory = storyMemoryStore?.load(book.storageDir, book.id, book.title)
        val previousTail = if (chapterIndex > 1) {
            contentStore.readZh(book.storageDir, chapterIndex - 1)?.takeLast(400).orEmpty()
        } else {
            ""
        }
        val config = settings.toTranslationConfig(memory, previousTail)
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
        val rawParagraphs = Paragraphs.split(raw)
        val zhParagraphs = Paragraphs.split(zh)
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
        val memory = storyMemoryStore?.load(book.storageDir, book.id, book.title)
        val previousTail = if (chapterIndex > 1) {
            contentStore.readZh(book.storageDir, chapterIndex - 1)?.takeLast(400).orEmpty()
        } else {
            ""
        }
        val config = settings.toTranslationConfig(memory, previousTail)
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
        val outcome = if (sidecar.status == "partial") {
            TranslationOutcome.Partial(newText, sidecar)
        } else {
            TranslationOutcome.Complete(newText, sidecar)
        }
        return commit(book, chapterIndex, outcome)
    }

    suspend fun polishChapter(
        book: BookEntity,
        chapterIndex: Int,
    ): TranslationOutcome {
        val raw = contentStore.readRaw(book.storageDir, chapterIndex)
            ?: return TranslationOutcome.Failed("这一章没有原文文件", false)
        val zh = contentStore.readZh(book.storageDir, chapterIndex)
            ?: return TranslationOutcome.Failed("这一章还没有译文，先翻译再润色", false)
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) {
            return TranslationOutcome.Failed("未配置翻译 API Key", false)
        }
        val memory = storyMemoryStore?.load(book.storageDir, book.id, book.title)
        val config = settings.toTranslationConfig(memory)
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val result = try {
            client.complete(
                messages = TranslationPrompts.polishMessages(raw, zh, config.promptContext()),
                model = config.model,
                maxTokens = config.maxTokens,
                temperature = 0.2,
            )
        } catch (error: TranslationException) {
            return TranslationOutcome.Failed("润色失败：${error.message}", error.retryable)
        }
        val cleaned = TranslationPrompts.cleanBlock(result.content)
        val issue = validatePolish(raw, zh, cleaned, config)
        if (issue != null) {
            return TranslationOutcome.Failed("润色未通过：$issue", true)
        }
        val oldSidecar = contentStore.readSidecar(book.storageDir, chapterIndex)
            ?: return TranslationOutcome.Failed("缺少章节翻译信息，无法安全写回", false)
        versionStore?.save(book.storageDir, chapterIndex, zh, oldSidecar)
        val tokens = ChapterTokens(
            input = oldSidecar.tokens.input + result.tokensIn,
            output = oldSidecar.tokens.output + result.tokensOut,
        )
        val cost = tokens.input / 1_000_000.0 * config.priceInCnyPerMillion +
            tokens.output / 1_000_000.0 * config.priceOutCnyPerMillion
        val sidecar = oldSidecar.copy(
            contentSha256 = Hashes.sha256(cleaned),
            translationConfigHash = config.cacheKey(),
            modelProvider = config.provider,
            modelId = config.model,
            promptVersion = config.promptVersion,
            translatedAt = java.time.Instant.now().toString(),
            tokens = tokens,
            cost = ChapterCost(amount = cost, currency = "CNY", estimated = true),
            glossaryRevision = config.storyRevision.takeIf { it.isNotBlank() }
                ?: config.glossaryRevision.takeIf { it.isNotBlank() },
            storyRevision = config.storyRevision.takeIf { it.isNotBlank() },
        )
        return if (sidecar.status == "partial") {
            commit(book, chapterIndex, TranslationOutcome.Partial(cleaned, sidecar))
        } else {
            commit(book, chapterIndex, TranslationOutcome.Complete(cleaned, sidecar))
        }
    }

    private fun validatePolish(
        raw: String,
        oldZh: String,
        newZh: String,
        config: TranslationConfig,
    ): String? {
        if (!TranslationValidators.detectChinese(newZh)) return "不是简体中文"
        val oldParagraphs = TranslationValidators.splitParagraphs(oldZh)
        val newParagraphs = TranslationValidators.splitParagraphs(newZh)
        if (oldParagraphs.size != newParagraphs.size) {
            return "段落数变化（${oldParagraphs.size} → ${newParagraphs.size}）"
        }
        val sourceParagraphs = TranslationValidators.splitParagraphs(raw)
        for (index in newParagraphs.indices) {
            val source = sourceParagraphs.getOrNull(index).orEmpty()
            val translated = newParagraphs[index]
            if (!TranslationValidators.hasTranslatable(source)) continue
            val issue = TranslationValidators.paragraphIssue(source, translated)
            if (issue != null) return "第 ${index + 1} 段：$issue"
            if (TranslationValidators.missingDialogue(source, translated)) {
                return "第 ${index + 1} 段对白疑似被合并"
            }
        }
        for (entry in config.glossary) {
            if (entry.source in raw && entry.target !in newZh) {
                return "锁定译名丢失：${entry.source} → ${entry.target}"
            }
        }
        val oldLength = oldZh.count { !it.isWhitespace() }.coerceAtLeast(1)
        val newLength = newZh.count { !it.isWhitespace() }
        val ratio = newLength.toDouble() / oldLength
        if (ratio < 0.60 || ratio > 1.70) {
            return "润色后长度异常（${"%.2f".format(ratio)} 倍）"
        }
        return null
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
