package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.kacyraho.lightnovel.reader.engine.ReaderTheme

@Composable
fun ReaderWorldlineSheet(
    chapterIndex: Int,
    initialText: String,
    state: ReaderWorldlineState,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onGenerate: (String) -> Unit,
    onOpenWorldlines: (() -> Unit)?,
) {
    var text by remember(initialText) { mutableStateOf(initialText) }
    val buttonColors = ButtonDefaults.buttonColors(
        containerColor = theme.text,
        contentColor = theme.background,
        disabledContainerColor = theme.secondary.copy(alpha = 0.25f),
        disabledContentColor = theme.secondary,
    )

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = theme.background,
            contentColor = theme.text,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .systemBarsPadding()
                    .imePadding()
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text(
                        "编辑正文",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = onDismiss) {
                        Text("取消", color = theme.text)
                    }
                    Button(
                        onClick = { onGenerate(text) },
                        enabled = !state.running && text.isNotBlank(),
                        colors = buttonColors,
                    ) {
                        Text(if (state.running) "生成中…" else "生成")
                    }
                }
                Text(
                    "第 $chapterIndex 章 · 修改会作为世界线起点",
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.secondary,
                )
                BasicTextField(
                    value = text,
                    onValueChange = { text = it },
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .verticalScroll(rememberScrollState()),
                    textStyle = TextStyle(
                        color = theme.text,
                        fontSize = 18.sp,
                        lineHeight = 30.sp,
                    ),
                    cursorBrush = SolidColor(theme.text),
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
                if (state.createdId != null && onOpenWorldlines != null) {
                    TextButton(onClick = onOpenWorldlines, modifier = Modifier.fillMaxWidth()) {
                        Text("查看世界线", color = theme.text)
                    }
                }
            }
        }
    }
}
