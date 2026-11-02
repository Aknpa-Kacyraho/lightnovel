package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.data.story.ChapterSummary
import com.kacyraho.lightnovel.data.story.CharacterCard
import com.kacyraho.lightnovel.data.story.StoryStyle

data class StoryPromptContext(
    val workId: String = "",
    val title: String = "",
    val glossary: List<GlossaryEntry> = emptyList(),
    val characters: List<CharacterCard> = emptyList(),
    val summaries: Map<Int, ChapterSummary> = emptyMap(),
    val style: StoryStyle = StoryStyle(),
    val lessons: List<String> = emptyList(),
    val previousChapterTail: String = "",
)

object TranslationPrompts {
    const val BATCH_SYSTEM =
        "你是一位资深日文轻小说译者，把日文轻小说翻译成简体中文。\n" +
            "目标：让中文读者读得顺，同时让每个角色还是他自己。\n" +
            "\n" +
            "【文体】\n" +
            "轻小说短句多、对话驱动、节奏快；叙述者的吐槽、偏见和自嘲是文本的一部分。" +
            "不要写成书面腔、成语堆砌或过度文艺化，也不要把吐槽改成正经陈述。\n" +
            "\n" +
            "【忠实与节奏】\n" +
            "不漏译、不增写、不解释、不总结；不要替角色补原文没有的心理或环境描写。" +
            "保留原文的段落、换行、短句和标点节奏；不要把碎句合并成一大段。" +
            "原文的重复和口语冗余如果是角色犹豫、拖延或撒娇的一部分，保留或压缩；纯填充才理顺。\n" +
            "\n" +
            "【角色声音】\n" +
            "同一句话会因角色和对谁说话而不同：冷淡、乖巧、傲娇、敬语角色要有不同的称呼、" +
            "语气词、句式和礼貌程度。按“角色×对象×场景”判断，不要只按性格类型定语气。" +
            "注意角色的词汇习惯和句法习惯，同一角色前后要一致；第一人称叙述者的偏见和吐槽要保留。\n" +
            "\n" +
            "【术语与文化】\n" +
            "人名、地名、技能名、组织名、称号严格按术语表和人物卡；术语表是锁定译名，不要擅自改动。" +
            "文化词保留日式风味，不过度本地化。双关优先功能对等改写，必要时才加短注。\n" +
            "\n" +
            "【对话与文字】\n" +
            "原文一个段落里可能连着好几行对白（行间没有空行）：每一行都要译出来，" +
            "不许只译第一句、不许合并成一句；译文保持同样的分行。\n" +
            "不许留假名：译文里不能出现日文假名（敬语、语气词、助词、专有名词都不行），" +
            "一律音译或意译成中文。原文本来就用英文/品牌名/缩写时照抄。" +
            "引号跟着原文：原文用「」就照用「」，用『』就照用『』，不要为了统一而替换。" +
            "\n" +
            "【输出】\n" +
            "只输出与输入相同编号、相同段数的简体中文译文，每段一行；" +
            "不要输出说明、标题、总结或额外注释列表。"

    const val SAKURA_SYSTEM =
        "你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，" +
            "并联系上下文正确使用人称代词，不擅自添加原文中没有的代词。"

    const val SAKURA_USER_PREFIX = "将下面的日文文本翻译成中文："

    fun batchMessages(
        chunk: List<TranslationValidators.IndexedParagraph>,
        context: String?,
        glossary: List<GlossaryEntry>,
    ): List<ChatMessage> = batchMessages(
        chunk,
        context,
        StoryPromptContext(glossary = glossary),
    )

    fun batchMessages(
        chunk: List<TranslationValidators.IndexedParagraph>,
        context: String?,
        story: StoryPromptContext,
    ): List<ChatMessage> = listOf(
        ChatMessage("system", BATCH_SYSTEM),
        ChatMessage("user", batchUserPrompt(chunk, context, story)),
    )

    fun sakuraMessages(
        block: String,
        context: String?,
        glossary: List<GlossaryEntry>,
    ): List<ChatMessage> = sakuraMessages(
        block,
        context,
        StoryPromptContext(glossary = glossary),
    )

    fun sakuraMessages(
        block: String,
        context: String?,
        story: StoryPromptContext,
    ): List<ChatMessage> = listOf(
        ChatMessage("system", sakuraSystemPrompt(block, context, story)),
        ChatMessage("user", "$SAKURA_USER_PREFIX$block"),
    )

    fun batchUserPrompt(
        chunk: List<TranslationValidators.IndexedParagraph>,
        context: String?,
        story: StoryPromptContext,
    ): String = buildString {
        val bodyText = chunk.joinToString("\n") { it.text }
        if (story.workId.isNotBlank()) {
            appendLine("【当前作品 work_id=${story.workId}】${story.title}")
            appendLine("下面的术语、人物、前情只属于本书；不要混入其它作品的设定。")
            appendLine()
        }
        if (!context.isNullOrBlank()) {
            appendLine("【前文译文（仅供衔接，不要重复翻译）】")
            appendLine(context.takeLast(1_200))
            appendLine()
        } else if (story.previousChapterTail.isNotBlank()) {
            appendLine("【上一章译文结尾（仅供衔接，不要重复翻译）】")
            appendLine(story.previousChapterTail.takeLast(1_200))
            appendLine()
        }

        val hitCharacters = story.characters.filter { card ->
            cardNames(card).any { it.isNotBlank() && it in bodyText }
        }
        val names = hitCharacters.flatMap(::cardNames)
        val summaries = story.summaries.values
            .sortedBy { it.index }
            .filter { summary -> names.any { it in summary.text } }
            .takeLast(3)
        if (summaries.isNotEmpty()) {
            appendLine("【前情梗概（保持人物与设定连贯）】")
            summaries.forEach { appendLine("第${it.index}话：${it.text.take(300)}") }
            appendLine()
        }

        val hits = story.glossary.filter { entry ->
            entry.source in bodyText || entry.aliases.any { it in bodyText }
        }
        if (hits.isNotEmpty()) {
            appendLine("【术语表（必须遵守）】")
            hits.take(30).forEach { appendLine("${it.source} => ${it.target}") }
            appendLine()
        }

        if (hitCharacters.isNotEmpty()) {
            appendLine("【登场人物（按角色卡保持声音；同一场景内必须可区分）】")
            hitCharacters.take(8).forEach { appendLine(characterCard(it)) }
            appendLine()
        }

        val style = story.style
        val styleLines = buildList {
            if (style.general.isNotBlank()) add("全篇风格：${style.general.take(300)}")
            if (style.narrator.isNotBlank()) add("叙述者滤镜：${style.narrator.take(300)}")
            if (style.honorifics.isNotBlank()) add("称谓处理：${style.honorifics.take(300)}")
            if (style.notes.isNotBlank()) add("特别注意：${style.notes.take(300)}")
            if (style.guide.isNotBlank()) add("本书补充翻译准则：${style.guide.take(1000)}")
        }
        if (styleLines.isNotEmpty()) {
            appendLine("【本书风格】")
            styleLines.forEach(::appendLine)
            appendLine()
        }
        if (story.lessons.isNotEmpty()) {
            appendLine("【本书经验（只适用于本书）】")
            story.lessons.takeLast(8).forEach { appendLine("- ${it.take(240)}") }
            appendLine()
        }

        appendLine("【原文段落（每段前的编号必须保留）】")
        chunk.forEachIndexed { i, paragraph ->
            append(i + 1)
            append(". ")
            appendLine(paragraph.text)
        }
        appendLine()
        appendLine("翻译时先判断每句是谁说的、对谁说；保持该角色的词汇和句法习惯。")
        appendLine("请输出同样段数、同样编号的简体中文译文，每段一行。")
    }

    fun sakuraSystemPrompt(
        block: String,
        context: String?,
        story: StoryPromptContext,
    ): String = buildString {
        append(SAKURA_SYSTEM)
        val hits = story.glossary.filter { entry ->
            entry.source in block || entry.aliases.any { it in block }
        }
        if (hits.isNotEmpty()) {
            append(" 术语译名：")
            append(hits.take(10).joinToString("；") { "${it.source}=${it.target}" })
            append("。")
        }
        val characters = story.characters.filter { card ->
            cardNames(card).any { it.isNotBlank() && it in block }
        }
        if (characters.isNotEmpty()) {
            append(" 登场人物：")
            append(
                characters.take(6).joinToString("；") {
                    "${it.source}=${it.target}" +
                        listOf(it.voice, it.address, it.notes)
                            .filter(String::isNotBlank)
                            .joinToString("，") { value -> value.take(80) }
                            .let { extra -> if (extra.isBlank()) "" else "（$extra）" }
                },
            )
            append("。")
        }
        if (story.style.general.isNotBlank()) {
            append(" 全篇风格：${story.style.general.take(200)}。")
        }
        if (!context.isNullOrBlank()) {
            append(" 上文译文片段（仅供理解人称，不要重复输出）：")
            append(context.replace("\n", " ").takeLast(320))
        } else if (story.previousChapterTail.isNotBlank()) {
            append(" 上一章结尾（仅供衔接，不要重复）：")
            append(story.previousChapterTail.replace("\n", " ").takeLast(320))
        }
        append(" 保留原文的段落与空行结构；只输出简体中文译文，不要编号、不要解释、不要输出原文。")
    }

    fun polishMessages(
        source: String,
        translation: String,
        story: StoryPromptContext,
    ): List<ChatMessage> = listOf(
        ChatMessage(
            "system",
            "你是轻小说译文的润色译者。只改写表达，不改变事实、人物关系、信息量或剧情顺序。" +
                "保留原文段落数、对白行数、术语表锁定译名和引号体系；" +
                "不要新增原文没有的动作、心理、解释或比喻；只输出润色后的简体中文译文，" +
                "段落之间用空行分隔，不要编号、不要说明。",
        ),
        ChatMessage("user", buildString {
            if (story.workId.isNotBlank()) {
                appendLine("【作品 work_id=${story.workId}】${story.title}")
            }
            val hits = story.glossary.filter { it.source in source }
            if (hits.isNotEmpty()) {
                appendLine("【锁定译名（必须保留）】")
                hits.take(30).forEach { appendLine("${it.source} => ${it.target}") }
            }
            val characters = story.characters.filter { card ->
                cardNames(card).any { it.isNotBlank() && it in source }
            }
            if (characters.isNotEmpty()) {
                appendLine("【人物声音】")
                characters.take(8).forEach { appendLine(characterCard(it)) }
            }
            if (story.style.general.isNotBlank()) {
                appendLine("【全篇风格】${story.style.general.take(300)}")
            }
            appendLine("【日文原文】")
            appendLine(source)
            appendLine("【当前译文】")
            appendLine(translation)
            appendLine("请输出润色后的译文。")
        }),
    )

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

    private fun cardNames(card: CharacterCard): List<String> =
        (listOf(card.source, card.target) + card.aliases).filter(String::isNotBlank)

    private fun characterCard(card: CharacterCard): String {
        val parts = buildList {
            if (card.target.isNotBlank()) add("译名：${card.target}")
            if (card.aliases.isNotEmpty()) add("别名：${card.aliases.joinToString("、")}")
            if (card.description.isNotBlank()) add("设定：${card.description.take(160)}")
            if (card.voice.isNotBlank()) add("语气：${card.voice.take(120)}")
            if (card.address.isNotBlank()) add("称呼：${card.address.take(120)}")
            if (card.lexicon.isNotBlank()) add("词汇习惯：${card.lexicon.take(120)}")
            if (card.syntax.isNotBlank()) add("句法习惯：${card.syntax.take(120)}")
            if (card.volume.isNotBlank()) add("本卷时间点：${card.volume.take(120)}")
            if (card.notes.isNotBlank()) add("注意：${card.notes.take(120)}")
        }
        return "${card.source}：" + parts.joinToString("；")
    }
}
