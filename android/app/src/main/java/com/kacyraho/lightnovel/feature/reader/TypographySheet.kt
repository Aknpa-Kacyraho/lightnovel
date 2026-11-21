package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.reader.engine.ReaderTheme
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TypographySheet(
    fontSizeSp: Float,
    lineHeight: Float,
    marginDp: Float,
    paragraphSpacing: Float,
    theme: ReaderTheme,
    onFontSizeChange: (Float) -> Unit,
    onLineHeightChange: (Float) -> Unit,
    onMarginChange: (Float) -> Unit,
    onParagraphSpacingChange: (Float) -> Unit,
    onReset: () -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var size by remember(fontSizeSp) { mutableFloatStateOf(fontSizeSp) }
    var line by remember(lineHeight) { mutableFloatStateOf(lineHeight) }
    var margin by remember(marginDp) { mutableFloatStateOf(marginDp) }
    var spacing by remember(paragraphSpacing) { mutableFloatStateOf(paragraphSpacing) }

    ModalBottomSheet(
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = theme.background,
        contentColor = theme.text,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("排版", style = MaterialTheme.typography.titleMedium, color = theme.text)
            TypographyRow(
                label = "字号",
                value = size,
                range = 12f..30f,
                display = String.format(Locale.US, "%.0f", size),
                theme = theme,
                onChange = { size = it },
                onCommit = { onFontSizeChange(size) },
            )
            TypographyRow(
                label = "行距",
                value = line,
                range = 1.2f..2.4f,
                display = String.format(Locale.US, "%.1f", line),
                theme = theme,
                onChange = { line = it },
                onCommit = { onLineHeightChange(line) },
            )
            TypographyRow(
                label = "左右边距",
                value = margin,
                range = 8f..48f,
                display = String.format(Locale.US, "%.0f", margin),
                theme = theme,
                onChange = { margin = it },
                onCommit = { onMarginChange(margin) },
            )
            TypographyRow(
                label = "段落间距",
                value = spacing,
                range = 0f..32f,
                display = String.format(Locale.US, "%.0f", spacing),
                theme = theme,
                onChange = { spacing = it },
                onCommit = { onParagraphSpacingChange(spacing) },
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = onReset) {
                    Text("恢复默认", color = theme.text)
                }
            }
        }
    }
}

@Composable
private fun TypographyRow(
    label: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    display: String,
    theme: ReaderTheme,
    onChange: (Float) -> Unit,
    onCommit: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = theme.text,
            modifier = Modifier.weight(1f),
        )
        Text(
            display,
            style = MaterialTheme.typography.labelMedium,
            color = theme.secondary,
        )
    }
    Slider(
        value = value,
        onValueChange = onChange,
        onValueChangeFinished = onCommit,
        valueRange = range,
        colors = SliderDefaults.colors(
            thumbColor = theme.text.copy(alpha = 0.75f),
            activeTrackColor = theme.text.copy(alpha = 0.45f),
            inactiveTrackColor = theme.secondary.copy(alpha = 0.25f),
        ),
    )
}
