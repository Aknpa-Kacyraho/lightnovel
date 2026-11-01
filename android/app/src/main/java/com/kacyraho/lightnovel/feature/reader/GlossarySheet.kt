package com.kacyraho.lightnovel.feature.reader

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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.reader.engine.ReaderTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GlossaryCorrectionSheet(
    entries: List<GlossaryEntry>,
    impact: GlossaryImpact?,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onSave: (GlossaryEntry) -> Unit,
    onDelete: (String) -> Unit,
    onSaveAndRetranslate: (GlossaryEntry) -> Unit,
    onEstimate: (String, List<String>) -> Unit,
) {
    var source by remember { mutableStateOf("") }
    var target by remember { mutableStateOf("") }
    var aliases by remember { mutableStateOf("") }

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
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("本书术语表", style = MaterialTheme.typography.titleMedium, color = theme.text)
            Text(
                "只作用于本书；保存后本章会标记为过期；重译时命中词强制使用这里的目标译名。",
                style = MaterialTheme.typography.bodySmall,
                color = theme.secondary,
            )
            Text(
                "影响范围：当前章节；费用按实际重译 token 计。",
                style = MaterialTheme.typography.bodySmall,
                color = theme.secondary,
            )
            if (entries.isNotEmpty()) {
                entries.forEach { entry ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "${entry.source} → ${entry.target}",
                            modifier = Modifier.weight(1f),
                            style = MaterialTheme.typography.bodyMedium,
                            color = theme.text,
                        )
                        TextButton(onClick = { onDelete(entry.id) }) {
                            Text("删除", color = theme.secondary)
                        }
                    }
                }
                HorizontalDivider(color = theme.secondary.copy(alpha = 0.3f))
            }
            OutlinedTextField(
                value = source,
                onValueChange = { source = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("原文 / 日文") },
                singleLine = true,
            )
            OutlinedTextField(
                value = target,
                onValueChange = { target = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("目标译名 / 中文") },
                singleLine = true,
            )
            OutlinedTextField(
                value = aliases,
                onValueChange = { aliases = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("别名，用逗号分隔") },
                singleLine = true,
            )
            val entry = GlossaryEntry(
                id = source.trim(),
                source = source.trim(),
                target = target.trim(),
                aliases = aliases.split(',', '，', '、')
                    .map(String::trim)
                    .filter(String::isNotBlank),
            )
            TextButton(
                onClick = { onEstimate(entry.source, entry.aliases) },
                enabled = entry.source.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("估算影响", color = theme.text)
            }
            if (impact != null) {
                Text(
                    "影响：${impact.chapters} 章 / ${impact.characters} 字 / 约 ¥${"%.4f".format(impact.costCny)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.secondary,
                )
            }
            Button(
                onClick = { onSave(entry) },
                enabled = entry.source.isNotBlank() && entry.target.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("保存术语")
            }
            TextButton(
                onClick = { onSaveAndRetranslate(entry) },
                enabled = entry.source.isNotBlank() && entry.target.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("保存并重译本章", color = theme.text)
            }
            TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("关闭", color = theme.text)
            }
        }
    }
}
