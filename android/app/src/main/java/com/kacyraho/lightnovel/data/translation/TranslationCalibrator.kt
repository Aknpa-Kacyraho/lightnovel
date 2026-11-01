package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.TranslationMode

data class CalibrationResult(
    val mode: TranslationMode,
    val maxChars: Int,
    val testedChars: Int,
    val maxTokens: Int,
    val latencyMs: Long,
    val tokensIn: Int,
    val tokensOut: Int,
    val note: String,
)

sealed interface CalibrationOutcome {
    data class Success(val result: CalibrationResult) : CalibrationOutcome
    data class Failure(val message: String) : CalibrationOutcome
}

class TranslationCalibrator {
    suspend fun probe(
        client: TranslationClient,
        model: String,
        maxTokens: Int,
        preferredMode: TranslationMode = TranslationMode.AUTO,
    ): CalibrationOutcome {
        val probe = CalibrationSample.probe()
        val modes = when (preferredMode) {
            TranslationMode.BATCH, TranslationMode.SAKURA -> listOf(preferredMode)
            TranslationMode.AUTO -> listOf(TranslationMode.BATCH, TranslationMode.SAKURA)
        }
        var lastError = "连接失败"
        for (mode in modes) {
            val attempt = if (mode == TranslationMode.SAKURA) {
                attemptSakura(client, model, maxTokens, probe.joinToString("\n\n"))
            } else {
                attemptBatch(client, model, maxTokens, probe)
            }
            if (attempt.ok) {
                return CalibrationOutcome.Success(
                    CalibrationResult(
                        mode = mode,
                        maxChars = 0,
                        testedChars = probe.sumOf { it.length },
                        maxTokens = maxTokens,
                        latencyMs = attempt.latencyMs,
                        tokensIn = attempt.tokensIn,
                        tokensOut = attempt.tokensOut,
                        note = "连接成功（${modeLabel(mode)}）。",
                    ),
                )
            }
            lastError = attempt.error ?: "连接失败"
            if (attempt.fatal) return CalibrationOutcome.Failure(lastError)
        }
        return CalibrationOutcome.Failure(lastError)
    }

    suspend fun calibrate(
        client: TranslationClient,
        model: String,
        maxTokens: Int,
        preferredMode: TranslationMode = TranslationMode.AUTO,
        isLocal: Boolean = false,
        onProgress: (String) -> Unit = {},
    ): CalibrationOutcome {
        val probe = CalibrationSample.probe()
        val mode = when (preferredMode) {
            TranslationMode.BATCH, TranslationMode.SAKURA -> preferredMode
            TranslationMode.AUTO -> {
                onProgress("正在识别翻译协议…")
                val batch = attemptBatch(client, model, maxTokens, probe)
                if (batch.ok) {
                    TranslationMode.BATCH
                } else {
                    val sakura = attemptSakura(
                        client,
                        model,
                        maxTokens,
                        probe.joinToString("\n\n"),
                    )
                    if (sakura.ok) {
                        TranslationMode.SAKURA
                    } else {
                        return CalibrationOutcome.Failure(
                            "无法识别翻译协议。编号模式：${batch.error}；Sakura 模式：${sakura.error}",
                        )
                    }
                }
            }
        }

        val candidates = when (mode) {
            TranslationMode.SAKURA -> listOf(3_000, 2_400, 1_800, 1_200)
            TranslationMode.BATCH -> if (isLocal) {
                listOf(3_000, 2_400, 1_800, 1_200)
            } else {
                listOf(6_000, 4_500, 3_000, 2_000)
            }
            TranslationMode.AUTO -> emptyList()
        }

        var lastError = "没有可用候选块大小"
        for (size in candidates) {
            onProgress("正在测试 ${size} 字/块（${modeLabel(mode)}）…")
            val paragraphs = CalibrationSample.paragraphs(size)
            val attempt = if (mode == TranslationMode.SAKURA) {
                attemptSakura(
                    client,
                    model,
                    maxTokens,
                    paragraphs.joinToString("\n\n"),
                )
            } else {
                attemptBatch(client, model, maxTokens, paragraphs)
            }
            if (attempt.ok) {
                val recommended = (size * 0.9).toInt().coerceAtLeast(800)
                return CalibrationOutcome.Success(
                    CalibrationResult(
                        mode = mode,
                        maxChars = recommended,
                        testedChars = size,
                        maxTokens = maxTokens,
                        latencyMs = attempt.latencyMs,
                        tokensIn = attempt.tokensIn,
                        tokensOut = attempt.tokensOut,
                        note = "实测 $size 字通过；留 10% 余量，按 $recommended 字/块。" +
                            "协议：${modeLabel(mode)}。",
                    ),
                )
            }
            lastError = attempt.error ?: "未知错误"
            if (attempt.fatal) {
                return CalibrationOutcome.Failure(lastError)
            }
        }
        return CalibrationOutcome.Failure("没有找到安全块大小；最后错误：$lastError")
    }

    private suspend fun attemptBatch(
        client: TranslationClient,
        model: String,
        maxTokens: Int,
        paragraphs: List<String>,
    ): Attempt {
        val indexed = paragraphs.mapIndexedNotNull { index, text ->
            if (TranslationValidators.hasTranslatable(text)) {
                TranslationValidators.IndexedParagraph(index, text)
            } else {
                null
            }
        }
        if (indexed.isEmpty()) return Attempt(false, error = "校准样本为空")
        val started = System.nanoTime()
        val completion = try {
            client.complete(
                messages = TranslationPrompts.batchMessages(indexed, null, emptyList()),
                model = model,
                maxTokens = maxTokens,
                temperature = 0.2,
            )
        } catch (error: Throwable) {
            return failureFrom(error)
        }
        val latency = (System.nanoTime() - started) / 1_000_000
        if (completion.finishReason == "length") {
            return Attempt(
                ok = false,
                error = "输出被截断（max_tokens 不足）",
                latencyMs = latency,
                tokensIn = completion.tokensIn,
                tokensOut = completion.tokensOut,
            )
        }
        val parsed = TranslationValidators.parseNumbered(completion.content)
        for ((offset, paragraph) in indexed.withIndex()) {
            val raw = parsed[offset + 1]
                ?: return Attempt(
                    false,
                    "缺少第 ${offset + 1} 段译文",
                    latency,
                    completion.tokensIn,
                    completion.tokensOut,
                )
            val zh = TranslationValidators.alignQuotes(raw, paragraph.text)
            val issue = TranslationValidators.paragraphIssue(paragraph.text, zh)
            if (issue != null) {
                return Attempt(
                    false,
                    "第 ${offset + 1} 段校验失败：$issue",
                    latency,
                    completion.tokensIn,
                    completion.tokensOut,
                )
            }
        }
        return Attempt(
            ok = true,
            latencyMs = latency,
            tokensIn = completion.tokensIn,
            tokensOut = completion.tokensOut,
        )
    }

    private suspend fun attemptSakura(
        client: TranslationClient,
        model: String,
        maxTokens: Int,
        block: String,
    ): Attempt {
        if (!TranslationValidators.hasTranslatable(block)) {
            return Attempt(false, error = "校准样本为空")
        }
        val started = System.nanoTime()
        val completion = try {
            client.complete(
                messages = TranslationPrompts.sakuraMessages(block, null, emptyList()),
                model = model,
                maxTokens = maxTokens,
                temperature = 0.2,
            )
        } catch (error: Throwable) {
            return failureFrom(error)
        }
        val latency = (System.nanoTime() - started) / 1_000_000
        if (completion.finishReason == "length") {
            return Attempt(
                ok = false,
                error = "输出被截断（max_tokens 不足）",
                latencyMs = latency,
                tokensIn = completion.tokensIn,
                tokensOut = completion.tokensOut,
            )
        }
        val cleaned = TranslationPrompts.cleanBlock(completion.content)
        val issue = TranslationValidators.blockIssue(block, cleaned)
        if (issue != null) {
            return Attempt(
                false,
                issue,
                latency,
                completion.tokensIn,
                completion.tokensOut,
            )
        }
        return Attempt(
            ok = true,
            latencyMs = latency,
            tokensIn = completion.tokensIn,
            tokensOut = completion.tokensOut,
        )
    }

    private fun failureFrom(error: Throwable): Attempt {
        val translation = error as? TranslationException
        val message = translation?.message ?: error.message ?: "请求失败"
        val fatal = translation == null ||
            translation.statusCode in setOf(400, 401, 403, 404, 422)
        return Attempt(false, message, fatal = fatal)
    }

    private fun modeLabel(mode: TranslationMode): String = when (mode) {
        TranslationMode.SAKURA -> "Sakura"
        TranslationMode.BATCH -> "编号批量"
        TranslationMode.AUTO -> "自动"
    }

    private data class Attempt(
        val ok: Boolean,
        val error: String? = null,
        val latencyMs: Long = 0,
        val tokensIn: Int = 0,
        val tokensOut: Int = 0,
        val fatal: Boolean = false,
    )
}
