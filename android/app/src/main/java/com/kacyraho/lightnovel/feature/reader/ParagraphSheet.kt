package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.reader.engine.ReaderTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ParagraphActionSheet(
    paragraph: ReaderParagraph,
    theme: ReaderTheme,
    enabled: Boolean,
    onDismiss: () -> Unit,
    onRetranslate: () -> Unit,
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
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("第 ${paragraph.id + 1} 段", style = MaterialTheme.typography.titleMedium, color = theme.text)
            Text("原文", style = MaterialTheme.typography.labelMedium, color = theme.secondary)
            Text(
                text = paragraph.source.ifBlank { "（空段）" },
                style = MaterialTheme.typography.bodyMedium,
                color = theme.text,
            )
            HorizontalDivider(color = theme.secondary.copy(alpha = 0.3f))
            Text("译文", style = MaterialTheme.typography.labelMedium, color = theme.secondary)
            Text(
                text = paragraph.translated ?: "尚未翻译",
                style = MaterialTheme.typography.bodyMedium,
                color = theme.text,
            )
            Text(
                "单段重译只替换这一段，不改变整章其他段落。",
                style = MaterialTheme.typography.bodySmall,
                color = theme.secondary,
            )
            TextButton(
                onClick = onRetranslate,
                enabled = enabled && paragraph.source.isNotBlank() && paragraph.translated != null,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("重译本段", color = theme.text)
            }
            TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("关闭", color = theme.text)
            }
        }
    }
}
