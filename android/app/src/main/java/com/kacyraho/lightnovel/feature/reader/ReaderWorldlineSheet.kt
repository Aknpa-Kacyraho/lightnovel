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
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.reader.engine.ReaderTheme
import com.kacyraho.lightnovel.ui.components.BrandFilterChip

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReaderWorldlineSheet(
    chapterIndex: Int,
    paragraphIndex: Int,
    contextText: String,
    state: ReaderWorldlineState,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onCreate: (String, String, String, String, String) -> Unit,
    onOpenWorldlines: (() -> Unit)?,
) {
    var title by remember { mutableStateOf("") }
    var character by remember { mutableStateOf("") }
    var action by remember { mutableStateOf("") }
    var constraint by remember { mutableStateOf("") }
    var mode by remember { mutableStateOf("exploration") }

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
            Text("从这里开世界线", style = MaterialTheme.typography.titleLarge, color = theme.text)
            Text(
                "分叉点：第 $chapterIndex 章第 ${paragraphIndex + 1} 段。生成会消耗 token，只使用分叉点之前的资料。",
                style = MaterialTheme.typography.bodySmall,
                color = theme.secondary,
            )
            if (contextText.isNotBlank()) {
                Text(
                    "当前段落：${contextText.take(180)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.secondary,
                )
            }
            OutlinedTextField(
                value = title,
                onValueChange = { title = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("分支标题（可空）") },
                singleLine = true,
                enabled = !state.running,
            )
            Text("模式", style = MaterialTheme.typography.titleSmall, color = theme.text)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                BrandFilterChip(
                    selected = mode == "exploration",
                    onClick = { mode = "exploration" },
                    label = { Text("探索型") },
                )
                BrandFilterChip(
                    selected = mode == "comparison",
                    onClick = { mode = "comparison" },
                    label = { Text("对照型") },
                )
            }
            OutlinedTextField(
                value = character,
                onValueChange = { character = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("要修改谁的行动（角色名）") },
                singleLine = true,
                enabled = !state.running,
            )
            OutlinedTextField(
                value = action,
                onValueChange = { action = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("改成什么行动") },
                minLines = 2,
                enabled = !state.running,
            )
            OutlinedTextField(
                value = constraint,
                onValueChange = { constraint = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("额外约束（可空）") },
                minLines = 2,
                enabled = !state.running,
            )
            if (state.running) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
            state.message?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (state.createdId != null) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        theme.secondary
                    },
                )
            }
            state.error?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }
            Button(
                onClick = {
                    onCreate(title, character, action, constraint, mode)
                },
                enabled = !state.running && character.isNotBlank() && action.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (state.running) "正在生成…" else "确定并生成世界线")
            }
            if (state.createdId != null && onOpenWorldlines != null) {
                TextButton(onClick = onOpenWorldlines, modifier = Modifier.fillMaxWidth()) {
                    Text("查看这条世界线", color = theme.text)
                }
            }
            TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("关闭", color = theme.text)
            }
        }
    }
}
