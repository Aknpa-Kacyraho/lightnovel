package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kacyraho.lightnovel.data.knowledge.EntityCard
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStatus
import com.kacyraho.lightnovel.data.knowledge.QueryEntry
import com.kacyraho.lightnovel.reader.engine.ReaderTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuerySheet(
    entries: List<QueryEntry>,
    status: KnowledgeStatus?,
    busy: Boolean,
    message: String?,
    error: String?,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onSelect: (String) -> Unit,
    onUpdate: () -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = entries.filter {
        query.isBlank() || it.displayName.contains(query, ignoreCase = true)
    }
    val groups = filtered.groupBy { it.type }
        .toList()
        .sortedBy { queryTypeOrder(it.first) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = theme.background,
        contentColor = theme.text,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp)
                .testTag("query-sheet"),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "附近词条",
                    style = MaterialTheme.typography.titleLarge,
                    color = theme.text,
                    modifier = Modifier.weight(1f),
                )
                if (filtered.isNotEmpty()) {
                    Text(
                        "${filtered.size} 条",
                        style = MaterialTheme.typography.labelMedium,
                        color = theme.secondary,
                    )
                }
            }
            Text(
                statusMessage(status),
                style = MaterialTheme.typography.bodySmall,
                color = theme.secondary,
            )
            Text(
                "只显示人物、地点、组织、物品；普通技能和概念不进查询。",
                style = MaterialTheme.typography.labelSmall,
                color = theme.secondary,
            )
            if (busy) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
            error?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.danger,
                )
            }
            if (!busy && error == null) {
                message?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = theme.secondary,
                    )
                }
            }
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("搜索已读词条") },
                singleLine = true,
                colors = readerOutlinedFieldColors(theme),
            )
            if (filtered.isEmpty()) {
                Text(
                    when {
                        status == null -> "本书还没有资料。先点下面更新本章资料。"
                        status.extractionUpdating -> "本章资料还没抽取完，点下面更新。"
                        else -> "本段没有可查询的人物、地点、组织或物品。"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.secondary,
                )
            } else {
                groups.forEach { (type, groupEntries) ->
                    Text(
                        typeLabel(type),
                        style = MaterialTheme.typography.titleSmall,
                        color = theme.secondary,
                        modifier = Modifier.padding(top = 10.dp, bottom = 2.dp),
                    )
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        color = theme.secondary.copy(alpha = 0.07f),
                        shape = RoundedCornerShape(14.dp),
                    ) {
                        Column {
                            groupEntries.forEachIndexed { index, entry ->
                                QueryEntryRow(
                                    entry = entry,
                                    theme = theme,
                                    onClick = { onSelect(entry.entityId) },
                                )
                                if (index != groupEntries.lastIndex) {
                                    HorizontalDivider(
                                        modifier = Modifier.padding(horizontal = 14.dp),
                                        color = theme.secondary.copy(alpha = 0.15f),
                                    )
                                }
                            }
                        }
                    }
                }
            }
            Button(
                onClick = onUpdate,
                enabled = !busy && status?.translationUpdating != true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
            ) {
                Text(
                    when {
                        busy -> "更新中…"
                        status == null -> "更新本章资料"
                        status.translationUpdating -> "本章翻译中"
                        status.extractionUpdating -> "更新本章资料"
                        else -> "重新更新本章资料"
                    },
                )
            }
            TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("关闭", color = theme.text)
            }
        }
    }
}

@Composable
private fun QueryEntryRow(
    entry: QueryEntry,
    theme: ReaderTheme,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                entry.displayName,
                style = MaterialTheme.typography.bodyLarge,
                color = theme.text,
            )
            Text(
                "${entry.visibleFactCount} 条已知资料",
                style = MaterialTheme.typography.labelMedium,
                color = theme.secondary,
            )
        }
        Spacer(Modifier.width(12.dp))
        Text("›", style = MaterialTheme.typography.titleLarge, color = theme.secondary)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EntityCardSheet(
    card: EntityCard,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onOpenChapter: (Int) -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = theme.background,
        contentColor = theme.text,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp)
                .testTag("entity-card-sheet"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.Top) {
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        card.entity.canonicalName,
                        style = MaterialTheme.typography.titleLarge,
                        color = theme.text,
                    )
                    val aliases = card.entity.aliases
                        .filter(String::isNotBlank)
                        .joinToString("、")
                    if (aliases.isNotBlank()) {
                        Text(
                            "别名：$aliases",
                            style = MaterialTheme.typography.bodySmall,
                            color = theme.secondary,
                        )
                    }
                }
                Spacer(Modifier.width(12.dp))
                Surface(
                    color = theme.secondary.copy(alpha = 0.12f),
                    shape = RoundedCornerShape(8.dp),
                ) {
                    Text(
                        typeLabel(card.entity.type),
                        style = MaterialTheme.typography.labelMedium,
                        color = theme.secondary,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                    )
                }
            }
            Text(
                "资料更新至第 ${card.status.canonExtractedThrough} 章",
                style = MaterialTheme.typography.labelMedium,
                color = theme.secondary,
            )
            if (card.facts.isNotEmpty()) {
                SectionTitle("已知资料", card.facts.size, theme)
                card.facts.forEach { fact ->
                    FactCard(
                        label = factKindLabel(fact.kind),
                        text = fact.text,
                        chapter = fact.sourceAnchor.chapter,
                        quote = fact.displayQuote ?: fact.sourceQuote,
                        theme = theme,
                        onOpenChapter = onOpenChapter,
                    )
                }
            }
            if (card.relations.isNotEmpty()) {
                SectionTitle("人物关系", card.relations.size, theme)
                card.relations.forEach { relation ->
                    val from = card.relatedNames[relation.fromEntityId] ?: "?"
                    val to = card.relatedNames[relation.toEntityId] ?: "?"
                    FactCard(
                        label = relation.label.ifBlank { "关系" },
                        text = "$from → $to",
                        chapter = relation.sourceAnchor.chapter,
                        quote = relation.displayQuote ?: relation.sourceQuote,
                        theme = theme,
                        onOpenChapter = onOpenChapter,
                    )
                }
            }
            if (card.voiceFacts.isNotEmpty()) {
                SectionTitle("语气 / 称呼", card.voiceFacts.size, theme)
                card.voiceFacts.forEach { voice ->
                    FactCard(
                        label = voice.dimension.ifBlank { "语气" },
                        text = voice.text,
                        chapter = voice.sourceAnchor.chapter,
                        quote = voice.exampleQuote ?: voice.displayQuote ?: voice.sourceQuote,
                        theme = theme,
                        onOpenChapter = onOpenChapter,
                    )
                }
            }
            if (card.facts.isEmpty() && card.relations.isEmpty() && card.voiceFacts.isEmpty()) {
                Text(
                    "当前进度还没有足够资料。",
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.secondary,
                )
            }
            TextButton(
                onClick = onDismiss,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 4.dp),
            ) {
                Text("关闭", color = theme.text)
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String, count: Int, theme: ReaderTheme) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.titleSmall,
            color = theme.text,
            modifier = Modifier.weight(1f),
        )
        Text(
            "$count 条",
            style = MaterialTheme.typography.labelSmall,
            color = theme.secondary,
        )
    }
    HorizontalDivider(color = theme.secondary.copy(alpha = 0.2f))
}

@Composable
private fun FactCard(
    label: String,
    text: String,
    chapter: Int,
    quote: String?,
    theme: ReaderTheme,
    onOpenChapter: (Int) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = theme.secondary.copy(alpha = 0.06f),
        shape = RoundedCornerShape(12.dp),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (label.isNotBlank()) {
                Text(
                    label,
                    style = MaterialTheme.typography.labelMedium,
                    color = theme.secondary,
                )
            }
            Text(
                text,
                style = MaterialTheme.typography.bodyLarge,
                color = theme.text,
                lineHeight = 24.sp,
            )
            if (!quote.isNullOrBlank()) {
                Surface(
                    color = theme.background.copy(alpha = 0.55f),
                    shape = RoundedCornerShape(8.dp),
                ) {
                    Text(
                        quote.take(200),
                        style = MaterialTheme.typography.bodySmall,
                        color = theme.secondary,
                        modifier = Modifier.padding(10.dp),
                    )
                }
            }
            TextButton(
                onClick = { onOpenChapter(chapter) },
                contentPadding = PaddingValues(0.dp),
            ) {
                Text(
                    "第 $chapter 章 · 查看出处",
                    style = MaterialTheme.typography.labelSmall,
                    color = theme.secondary,
                )
            }
        }
    }
}

private fun statusMessage(status: KnowledgeStatus?): String = when {
    status == null -> "还没有资料"
    status.translationUpdating -> "本章翻译中"
    status.extractionUpdating -> "资料更新中"
    status.locationDegraded -> "定位失败，只显示前一章及更早资料"
    else -> "资料更新至第 ${status.canonExtractedThrough} 章"
}

private fun typeLabel(type: String): String = when (type) {
    "character" -> "人物"
    "place" -> "地点"
    "organization" -> "组织"
    "item" -> "物品"
    "skill" -> "技能"
    "concept" -> "概念"
    else -> type
}

private fun queryTypeOrder(type: String): Int = when (type) {
    "character" -> 0
    "place" -> 1
    "organization" -> 2
    "item" -> 3
    "skill" -> 4
    "concept" -> 5
    else -> 6
}

private fun factKindLabel(kind: String): String = when (kind) {
    "persona" -> "人物资料"
    "direction" -> "剧情走向"
    "event" -> "事件"
    "reveal_constraint" -> "伏笔"
    else -> kind
}
