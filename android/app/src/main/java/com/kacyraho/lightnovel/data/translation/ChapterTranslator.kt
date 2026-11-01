package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.TranslationMode
import com.kacyraho.lightnovel.core.storage.ChapterCost
import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.ChapterTokens
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.data.story.ChapterSummary
import com.kacyraho.lightnovel.data.story.CharacterCard
import com.kacyraho.lightnovel.data.story.StoryStyle
import java.time.Instant
import kotlinx.coroutines.delay

data class TranslationConfig(
    val model: String = "deepseek-flash",
    val maxChars: Int = 3_000,
    val maxTokens: Int = 8_192,
    val temperature: Double = 0.2,
    val promptVersion: String = "android-a2-v3",
    val mode: TranslationMode = TranslationMode.BATCH,
    val provider: String = "deepseek",
    val priceInCnyPerMillion: Double = 2.0,
    val priceOutCnyPerMillion: Double = 8.0,
    val glossary: List<GlossaryEntry> = emptyList(),
    val glossaryRevision: String = "",
    val workId: String = "",
    val workTitle: String = "",
    val characters: List<CharacterCard> = emptyList(),
    val summaries: Map<Int, ChapterSummary> = emptyMap(),
    val style: StoryStyle = StoryStyle(),
    val lessons: List<String> = emptyList(),
    val storyRevision: String = "",
    val previousChapterTail: String = "",
) {
    fun cacheKey(): String = Hashes.sha256(
        listOf(
            model,
            promptVersion,
            mode.wire,
            storyRevision.ifBlank { glossaryRevision },
        ).joinToString("|"),
    )

    fun legacyCacheKey(): String = Hashes.sha256(
        listOf(
            model,
            "android-a2-v2",
            3_000,
            8_192,
            0.2,
            glossaryRevision,
        ).joinToString("|"),
    )

    fun acceptsSidecarHash(hash: String?): Boolean =
        hash == cacheKey() || hash == legacyCacheKey()
}

sealed interface TranslationOutcome {
    data class Complete(
        val text: String,
        val sidecar: ChapterSidecar,
    ) : TranslationOutcome

    data class Partial(
        val text: String,
        val sidecar: ChapterSidecar,
    ) : TranslationOutcome

    data class Failed(
        val reason: String,
        val retryable: Boolean,
    ) : TranslationOutcome
}

class ChapterTranslator(
    private val client: TranslationClient,
    private val store: TranslationStore,
) {
    suspend fun translate(
        storageDir: String,
        chapterIndex: Int,
        sourceText: String,
        config: TranslationConfig = TranslationConfig(),
        onProgress: (done: Int, total: Int) -> Unit = { _, _ -> },
    ): TranslationOutcome {
        val paragraphs = TranslationValidators.splitParagraphs(sourceText)
        val indexed = paragraphs.mapIndexedNotNull { index, text ->
            if (TranslationValidators.hasTranslatable(text)) {
                TranslationValidators.IndexedParagraph(index, text)
            } else {
                null
            }
        }
        if (indexed.isEmpty()) {
            val sourceSha = Hashes.sha256(sourceText)
            val sidecar = sidecar(
                sourceSha = sourceSha,
                contentSha = Hashes.sha256(sourceText),
                configHash = config.cacheKey(),
                config = config,
                tokensIn = 0,
                tokensOut = 0,
                incomplete = emptyList(),
            )
            return TranslationOutcome.Complete(sourceText, sidecar)
        }
        return when (config.mode) {
            TranslationMode.SAKURA -> translateSakura(
                storageDir = storageDir,
                chapterIndex = chapterIndex,
                sourceText = sourceText,
                paragraphs = paragraphs,
                indexed = indexed,
                config = config,
                onProgress = onProgress,
            )
            else -> translateBatch(
                storageDir = storageDir,
                chapterIndex = chapterIndex,
                sourceText = sourceText,
                paragraphs = paragraphs,
                indexed = indexed,
                config = config,
                onProgress = onProgress,
            )
        }
    }

    private suspend fun translateBatch(
        storageDir: String,
        chapterIndex: Int,
        sourceText: String,
        paragraphs: List<String>,
        indexed: List<TranslationValidators.IndexedParagraph>,
        config: TranslationConfig,
        onProgress: (done: Int, total: Int) -> Unit,
    ): TranslationOutcome {
        val sourceSha = Hashes.sha256(sourceText)
        val configHash = config.cacheKey()
        val translated = linkedMapOf<Int, String>()
        var tokensIn = 0
        var tokensOut = 0
        val cached = loadCache(storageDir, chapterIndex, sourceSha, config)
        if (cached != null) {
            for (paragraph in cached.paragraphs) {
                val source = indexed.firstOrNull { it.index == paragraph.index } ?: continue
                if (paragraph.sourceHash == Hashes.sha256(source.text)) {
                    translated[paragraph.index] = paragraph.text
                }
            }
            tokensIn += cached.tokensIn
            tokensOut += cached.tokensOut
        }

        val sourceByIndex = indexed.associateBy { it.index }
        val chunks = TranslationValidators.chunkIndexed(indexed, config.maxChars)
        var done = translated.size
        val total = indexed.size
        var context: String? = null
        onProgress(done, total)

        for (chunk in chunks) {
            val missing = chunk.filter { it.index !in translated }
            if (missing.isEmpty()) {
                context = chunk.lastOrNull()
                    ?.let { translated[it.index] }
                    ?.takeLast(400)
                continue
            }

            val result = translateChunk(missing, sourceByIndex, config, context)
            context = result.translated[missing.last().index]?.takeLast(400)
                ?: missing.last().text.takeLast(400)
            translated.putAll(result.translated)
            tokensIn += result.tokensIn
            tokensOut += result.tokensOut
            done += result.translated.size
            onProgress(done, total)

            val cache = ChapterCache(
                sourceSha256 = sourceSha,
                configHash = configHash,
                paragraphs = translated.map { (index, text) ->
                    CachedParagraph(
                        index = index,
                        sourceHash = Hashes.sha256(sourceByIndex.getValue(index).text),
                        text = text,
                    )
                },
                model = config.model,
                tokensIn = tokensIn,
                tokensOut = tokensOut,
            )
            store.save(storageDir, chapterIndex, cache)
        }

        val output = paragraphs.mapIndexed { index, text ->
            translated[index] ?: text
        }.joinToString("\n")
        val incomplete = indexed.map { it.index }.filter { it !in translated }
        val sidecar = sidecar(
            sourceSha = sourceSha,
            contentSha = Hashes.sha256(output),
            configHash = configHash,
            config = config,
            tokensIn = tokensIn,
            tokensOut = tokensOut,
            incomplete = incomplete,
        )
        return if (incomplete.isEmpty()) {
            TranslationOutcome.Complete(output, sidecar)
        } else {
            TranslationOutcome.Partial(output, sidecar)
        }
    }

    private suspend fun translateSakura(
        storageDir: String,
        chapterIndex: Int,
        sourceText: String,
        paragraphs: List<String>,
        indexed: List<TranslationValidators.IndexedParagraph>,
        config: TranslationConfig,
        onProgress: (done: Int, total: Int) -> Unit,
    ): TranslationOutcome {
        val sourceSha = Hashes.sha256(sourceText)
        val configHash = config.cacheKey()
        val ranges = TranslationValidators.blockRanges(paragraphs, config.maxChars)
        val cached = loadCache(storageDir, chapterIndex, sourceSha, config)
        val cachedBlocks = cached?.blocks.orEmpty()
            .filter { it.sourceHash.isNotBlank() }
            .associateBy { it.index }
        var tokensIn = cached?.tokensIn ?: 0
        var tokensOut = cached?.tokensOut ?: 0
        val translatedBlocks = linkedMapOf<Int, String>()
        val outputs = linkedMapOf<Int, String>()
        val incomplete = mutableSetOf<Int>()
        var done = 0
        val total = indexed.size
        var context: String? = null
        onProgress(done, total)

        for ((blockIndex, range) in ranges.withIndex()) {
            val block = paragraphs.subList(range.first, range.last + 1).joinToString("\n")
            val cachedBlock = cachedBlocks[blockIndex]
            if (cachedBlock != null && cachedBlock.sourceHash == Hashes.sha256(block)) {
                translatedBlocks[blockIndex] = cachedBlock.text
                outputs[blockIndex] = cachedBlock.text
                context = cachedBlock.text.takeLast(400)
                done += range.count { TranslationValidators.hasTranslatable(paragraphs[it]) }
                onProgress(done, total)
                continue
            }

            val result = translateSakuraBlock(block, config, context)
            val text = result.text
            if (text != null) {
                translatedBlocks[blockIndex] = text
                outputs[blockIndex] = text
                tokensIn += result.tokensIn
                tokensOut += result.tokensOut
                context = text.takeLast(400)
            } else {
                outputs[blockIndex] = block
                context = block.takeLast(400)
                range.forEach { index ->
                    if (TranslationValidators.hasTranslatable(paragraphs[index])) {
                        incomplete += index
                    }
                }
            }
            done += range.count { TranslationValidators.hasTranslatable(paragraphs[it]) }
            onProgress(done, total)

            store.save(
                storageDir,
                chapterIndex,
                ChapterCache(
                    sourceSha256 = sourceSha,
                    configHash = configHash,
                    blocks = translatedBlocks.map { (index, value) ->
                        val blockRange = ranges[index]
                        CachedBlock(
                            index = index,
                            sourceHash = Hashes.sha256(
                                paragraphs.subList(
                                    blockRange.first,
                                    blockRange.last + 1,
                                ).joinToString("\n"),
                            ),
                            text = value,
                        )
                    },
                    model = config.model,
                    tokensIn = tokensIn,
                    tokensOut = tokensOut,
                ),
            )
        }

        val output = ranges.mapIndexed { index, _ ->
            outputs[index] ?: paragraphs.subList(
                ranges[index].first,
                ranges[index].last + 1,
            ).joinToString("\n")
        }.joinToString("\n")
        val sidecar = sidecar(
            sourceSha = sourceSha,
            contentSha = Hashes.sha256(output),
            configHash = configHash,
            config = config,
            tokensIn = tokensIn,
            tokensOut = tokensOut,
            incomplete = incomplete.sorted(),
        )
        return if (incomplete.isEmpty()) {
            TranslationOutcome.Complete(output, sidecar)
        } else {
            TranslationOutcome.Partial(output, sidecar)
        }
    }

    suspend fun translateOne(
        sourceText: String,
        config: TranslationConfig = TranslationConfig(),
    ): ParagraphResult? {
        if (config.mode == TranslationMode.SAKURA) {
            val block = translateSakuraBlock(sourceText, config, null)
            return block.text?.let { ParagraphResult(it, block.tokensIn, block.tokensOut) }
        }
        val indexed = TranslationValidators.IndexedParagraph(0, sourceText)
        repeat(2) {
            try {
                val result = client.complete(
                    messages = TranslationPrompts.batchMessages(
                        listOf(indexed),
                        null,
                        config.promptContext(),
                    ),
                    model = config.model,
                    maxTokens = config.maxTokens,
                    temperature = config.temperature,
                )
                val raw = TranslationValidators.parseNumbered(result.content)[1] ?: return@repeat
                val zh = TranslationValidators.alignQuotes(raw, sourceText)
                if (TranslationValidators.paragraphIssue(sourceText, zh) == null) {
                    return ParagraphResult(zh, result.tokensIn, result.tokensOut)
                }
            } catch (_: TranslationException) {
                // retry once; the caller reports a single failure
            }
            delay(400)
        }
        return null
    }

    data class ParagraphResult(
        val text: String,
        val tokensIn: Int,
        val tokensOut: Int,
    )

    private fun loadCache(
        storageDir: String,
        chapterIndex: Int,
        sourceSha: String,
        config: TranslationConfig,
    ): ChapterCache? = store.load(storageDir, chapterIndex, sourceSha, config.cacheKey())
        ?: store.load(storageDir, chapterIndex, sourceSha, config.legacyCacheKey())

    private suspend fun translateSakuraBlock(
        block: String,
        config: TranslationConfig,
        context: String?,
    ): SakuraBlockResult {
        var lastError: String? = null
        for (attempt in 1..3) {
            try {
                val result = client.complete(
                    messages = TranslationPrompts.sakuraMessages(
                        block,
                        context,
                        config.promptContext(),
                    ),
                    model = config.model,
                    maxTokens = config.maxTokens,
                    temperature = config.temperature,
                )
                if (result.finishReason == "length") {
                    lastError = "输出被截断（max_tokens 不足）"
                    break
                }
                val cleaned = TranslationPrompts.cleanBlock(result.content)
                val issue = TranslationValidators.blockIssue(block, cleaned)
                if (issue == null) {
                    return SakuraBlockResult(
                        text = cleaned,
                        tokensIn = result.tokensIn,
                        tokensOut = result.tokensOut,
                    )
                }
                lastError = issue
                delay(400L * attempt)
            } catch (e: TranslationException) {
                lastError = e.message
                if (!e.retryable) break
                if (attempt == 3) break
                delay(600L * attempt)
            }
        }
        return SakuraBlockResult(null, 0, 0, lastError)
    }

    private suspend fun translateChunk(
        chunk: List<TranslationValidators.IndexedParagraph>,
        sourceByIndex: Map<Int, TranslationValidators.IndexedParagraph>,
        config: TranslationConfig,
        context: String?,
    ): ChunkResult {
        var lastError: String? = null
        for (attempt in 1..3) {
            try {
                val result = client.complete(
                    messages = TranslationPrompts.batchMessages(
                        chunk,
                        context,
                        config.promptContext(),
                    ),
                    model = config.model,
                    maxTokens = config.maxTokens,
                    temperature = config.temperature,
                )
                val parsed = TranslationValidators.parseNumbered(result.content)
                val accepted = linkedMapOf<Int, String>()
                val failed = mutableSetOf<Int>()
                chunk.forEachIndexed { i, paragraph ->
                    val raw = parsed[i + 1]
                    val source = sourceByIndex.getValue(paragraph.index)
                    if (raw == null) {
                        failed += paragraph.index
                        lastError = "缺少第 ${i + 1} 段译文"
                    } else {
                        val zh = TranslationValidators.alignQuotes(raw, paragraph.text)
                        val issue = TranslationValidators.paragraphIssue(paragraph.text, zh)
                        if (issue != null) {
                            failed += paragraph.index
                            lastError = "第 ${i + 1} 段校验未通过：$issue"
                        } else {
                            accepted[paragraph.index] = zh
                        }
                    }
                }
                if (failed.isEmpty()) {
                    return ChunkResult(
                        translated = accepted,
                        tokensIn = result.tokensIn,
                        tokensOut = result.tokensOut,
                    )
                }
                if (attempt == 3) {
                    return ChunkResult(
                        translated = accepted,
                        tokensIn = result.tokensIn,
                        tokensOut = result.tokensOut,
                        failed = failed,
                    )
                }
                delay(400L * attempt)
            } catch (e: TranslationException) {
                lastError = e.message
                if (!e.retryable) {
                    return ChunkResult(emptyMap(), 0, 0, chunk.map { it.index }.toSet())
                }
                if (attempt == 3) break
                delay(600L * attempt)
            }
        }
        return ChunkResult(
            translated = emptyMap(),
            tokensIn = 0,
            tokensOut = 0,
            failed = chunk.map { it.index }.toSet(),
            error = lastError,
        )
    }

    private fun sidecar(
        sourceSha: String,
        contentSha: String,
        configHash: String,
        config: TranslationConfig,
        tokensIn: Int,
        tokensOut: Int,
        incomplete: List<Int>,
    ): ChapterSidecar {
        val cost = tokensIn / 1_000_000.0 * config.priceInCnyPerMillion +
            tokensOut / 1_000_000.0 * config.priceOutCnyPerMillion
        return ChapterSidecar(
            status = if (incomplete.isEmpty()) "complete" else "partial",
            sourceSha256 = sourceSha,
            contentSha256 = contentSha,
            translationConfigHash = configHash,
            modelProvider = config.provider,
            modelRole = "translate",
            modelId = config.model,
            promptVersion = config.promptVersion,
            translatedAt = Instant.now().toString(),
            tokens = ChapterTokens(tokensIn, tokensOut),
            cost = ChapterCost(amount = cost, currency = "CNY", estimated = true),
            incompleteParagraphs = incomplete,
            incompleteReason = if (incomplete.isEmpty()) null else "provider_incomplete",
            glossaryRevision = config.storyRevision.takeIf { it.isNotBlank() }
                ?: config.glossaryRevision.takeIf { it.isNotBlank() },
            storyRevision = config.storyRevision.takeIf { it.isNotBlank() },
        )
    }

    private data class ChunkResult(
        val translated: Map<Int, String>,
        val tokensIn: Int,
        val tokensOut: Int,
        val failed: Set<Int> = emptySet(),
        val error: String? = null,
    )

    private data class SakuraBlockResult(
        val text: String?,
        val tokensIn: Int,
        val tokensOut: Int,
        val error: String? = null,
    )
}

internal fun TranslationConfig.promptContext(): StoryPromptContext = StoryPromptContext(
    workId = workId,
    title = workTitle,
    glossary = glossary,
    characters = characters,
    summaries = summaries,
    style = style,
    lessons = lessons,
    previousChapterTail = previousChapterTail,
)

