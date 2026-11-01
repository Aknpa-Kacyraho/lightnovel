package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.data.glossary.GlossaryEntry

object TranslationPrompts {
    const val BATCH_SYSTEM =
        "你是日文轻小说到简体中文的翻译器。你的任务是忠实翻译，不是摘要、改写或续写。\n" +
            "硬规则：\n" +
            "1. 只翻译【待翻译段落】。输入中的每个编号必须在输出中对应且只对应一次，" +
            "编号和顺序不得改变；不得合并、拆分、遗漏或新增段落。\n" +
            "2. 原文一个段落对应译文一个段落。原文一段内有连续多行对白时，保留换行逐行译出，" +
            "不许只译第一句。\n" +
            "3. 不添加原文没有的主语、代词、称呼、动作、心理描写、背景解释或语气词。" +
            "日文省略主语时中文可以省略；无法确定时保持模糊，不得臆造。\n" +
            "4. 不总结、不改写、不续写，不删减或弱化原文内容。\n" +
            "5. 保留原文的「」『』等引号字符，不增删、不替换、不统一字形；" +
            "不可翻的分隔线、纯符号、纯数字、颜文字原样输出。\n" +
            "6. 【前文语境】只供理解，不得翻译或复述。\n" +
            "7. 如果提供了【术语表】，命中词必须使用表内译名；表外专有名词保留原文，不擅自意译。\n" +
            "8. 只输出编号和译文，每段一行；不要解释、标题、JSON 或 Markdown 代码块。"

    const val SAKURA_SYSTEM =
        "你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，" +
            "并联系上下文正确使用人称代词，不擅自添加原文中没有的代词。"

    const val SAKURA_USER_PREFIX = "将下面的日文文本翻译成中文："

    fun batchMessages(
        chunk: List<TranslationValidators.IndexedParagraph>,
        context: String?,
        glossary: List<GlossaryEntry>,
    ): List<ChatMessage> = listOf(
        ChatMessage("system", BATCH_SYSTEM),
        ChatMessage("user", batchUserPrompt(chunk, context, glossary)),
    )

    fun sakuraMessages(
        block: String,
        context: String?,
        glossary: List<GlossaryEntry>,
    ): List<ChatMessage> = listOf(
        ChatMessage("system", sakuraSystemPrompt(block, context, glossary)),
        ChatMessage("user", "$SAKURA_USER_PREFIX$block"),
    )

    fun batchUserPrompt(
        chunk: List<TranslationValidators.IndexedParagraph>,
        context: String?,
        glossary: List<GlossaryEntry>,
    ): String = buildString {
        if (!context.isNullOrBlank()) {
            appendLine("【前文语境，仅供理解，不要翻译，不要输出】")
            appendLine(context)
        }
        val text = chunk.joinToString("\n") { it.text }
        val hits = glossary.filter { entry ->
            entry.source in text || entry.aliases.any { it in text }
        }
        if (hits.isNotEmpty()) {
            appendLine("【术语表，必须优先使用】")
            hits.forEach { entry ->
                append(entry.source)
                append(" -> ")
                appendLine(entry.target)
            }
        }
        appendLine("【待翻译段落】")
        chunk.forEachIndexed { i, paragraph ->
            append(i + 1)
            append(". ")
            appendLine(paragraph.text)
        }
    }

    fun sakuraSystemPrompt(
        block: String,
        context: String?,
        glossary: List<GlossaryEntry>,
    ): String = buildString {
        append(SAKURA_SYSTEM)
        val hits = glossary.filter { entry ->
            entry.source in block || entry.aliases.any { it in block }
        }
        if (hits.isNotEmpty()) {
            append(" 术语译名：")
            append(hits.take(10).joinToString("；") { "${it.source}=${it.target}" })
            append("。")
        }
        if (!context.isNullOrBlank()) {
            append(" 上文译文片段（仅供理解人称，不要重复输出）：")
            append(context.replace("\n", " ").takeLast(160))
        }
        append(" 保留原文的段落与空行结构；只输出简体中文译文，不要编号、不要解释、不要输出原文。")
    }

    fun cleanBlock(reply: String): String {
        var text = reply.replace("\r\n", "\n").trim()
        text = text.removePrefix("```").removeSuffix("```").trim()
        text = text.removePrefix("简体中文").trim()
        text = text.removePrefix("中文译文").trim()
        text = text.removePrefix("译文：").trim()
        if (text.startsWith(SAKURA_USER_PREFIX)) {
            text = text.removePrefix(SAKURA_USER_PREFIX).trim()
        }
        return text
    }
}
