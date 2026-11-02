package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.data.knowledge.EntityCard
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStatus
import com.kacyraho.lightnovel.data.knowledge.QueryEntry
import com.kacyraho.lightnovel.reader.engine.ReaderTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuerySheet(
    entries: List<QueryEntry>,
    status: KnowledgeStatus?,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onSelect: (String) -> Unit,
    onUpdate: () -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = entries.filter {
        query.isBlank() || it.displayName.contains(query, ignoreCase = true)
    }
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
            Text("本页词条", style = MaterialTheme.typography.titleMedium, color = theme.text)
            Text(
                statusMessage(status),
                style = MaterialTheme.typography.bodySmall,
                color = theme.secondary,
            )
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("搜索已读词条") },
                singleLine = true,
            )
            if (filtered.isEmpty()) {
                Text(
                    when {
                        status == null -> "本书还没有资料。先点下面更新本章资料。"
                        status.extractionUpdating -> "本章资料还没抽取完，点下面更新。"
                        else -> "本段没有可查询的词条。"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.secondary,
                )
            } else {
                filtered.forEach { entry ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onSelect(entry.entityId) }
                            .padding(vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(entry.displayName, color = theme.text)
                            Text(
                                "${typeLabel(entry.type)} · ${entry.visibleFactCount} 条已知信息",
                                style = MaterialTheme.typography.bodySmall,
                                color = theme.secondary,
                            )
                        }
                        Text("›", color = theme.secondary)
                    }
                    HorizontalDivider(color = theme.secondary.copy(alpha = 0.2f))
                }
            }
            Button(
                onClick = onUpdate,
                enabled = status?.translationUpdating != true,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    when {
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
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(card.entity.canonicalName, style = MaterialTheme.typography.titleLarge, color = theme.text)
            Text(
                "${typeLabel(card.entity.type)} · 资料更新至第 ${card.status.canonExtractedThrough} 章",
                style = MaterialTheme.typography.bodySmall,
                color = theme.secondary,
            )
            if (card.facts.isNotEmpty()) {
                SectionTitle("已知信息", theme)
                card.facts.forEach { fact ->
                    FactRow(
                        text = fact.text,
                        chapter = fact.sourceAnchor.chapter,
                        quote = fact.displayQuote ?: fact.sourceQuote,
                        theme = theme,
                        onOpenChapter = onOpenChapter,
                    )
                }
            }
            if (card.relations.isNotEmpty()) {
                SectionTitle("关系", theme)
                card.relations.forEach { relation ->
                    val from = card.relatedNames[relation.fromEntityId] ?: "?"
                    val to = card.relatedNames[relation.toEntityId] ?: "?"
                    FactRow(
                        text = "$from → $to：${relation.label}",
                        chapter = relation.sourceAnchor.chapter,
                        quote = relation.displayQuote ?: relation.sourceQuote,
                        theme = theme,
                        onOpenChapter = onOpenChapter,
                    )
                }
            }
            if (card.voiceFacts.isNotEmpty()) {
                SectionTitle("语气 / 称呼", theme)
                card.voiceFacts.forEach { voice ->
                    FactRow(
                        text = "${voice.dimension}：${voice.text}",
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
            TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("关闭", color = theme.text)
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String, theme: ReaderTheme) {
    Text(text, style = MaterialTheme.typography.titleSmall, color = theme.text)
}

@Composable
private fun FactRow(
    text: String,
    chapter: Int,
    quote: String?,
    theme: ReaderTheme,
    onOpenChapter: (Int) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(text, color = theme.text, style = MaterialTheme.typography.bodyMedium)
        if (!quote.isNullOrBlank()) {
            Text(
                quote.take(160),
                color = theme.secondary,
                style = MaterialTheme.typography.bodySmall,
            )
        }
        TextButton(onClick = { onOpenChapter(chapter) }) {
            Text("第 $chapter 章 · 跳到该章", color = theme.secondary)
        }
    }
}

private fun statusMessage(status: KnowledgeStatus?): String = when {
    status == null -> "资料状态未知"
    status.translationUpdating -> "本章翻译中，资料会在翻译完成后更新"
    status.extractionUpdating -> "本章资料更新中"
    status.locationDegraded -> "本章段落定位失败，只显示前一章及更早的资料"
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
