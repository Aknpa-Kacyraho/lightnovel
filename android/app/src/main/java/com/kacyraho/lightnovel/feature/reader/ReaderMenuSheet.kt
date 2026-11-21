package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ReaderMenuSheet(
    items: List<ReaderMenuItem>,
    backgroundColor: Color,
    textColor: Color,
    secondaryColor: Color,
    onDismiss: () -> Unit,
    onSelect: (ReaderMenuItem) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = backgroundColor,
        contentColor = textColor,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.7f)
                .verticalScroll(rememberScrollState())
                .padding(bottom = 20.dp),
        ) {
            Text(
                "更多",
                style = MaterialTheme.typography.titleMedium,
                color = textColor,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
            )
            var renderedGroup: ReaderMenuGroup? = null
            items.forEach { item ->
                if (item.group != renderedGroup) {
                    if (renderedGroup != null) {
                        HorizontalDivider(
                            color = secondaryColor.copy(alpha = 0.2f),
                            modifier = Modifier.padding(vertical = 4.dp),
                        )
                    }
                    Text(
                        item.group.label,
                        style = MaterialTheme.typography.labelMedium,
                        color = secondaryColor,
                        modifier = Modifier.padding(
                            start = 20.dp,
                            top = 8.dp,
                            end = 20.dp,
                            bottom = 4.dp,
                        ),
                    )
                    renderedGroup = item.group
                }
                Text(
                    item.label,
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (item.enabled) textColor else secondaryColor.copy(alpha = 0.5f),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(enabled = item.enabled) { onSelect(item) }
                        .padding(horizontal = 20.dp, vertical = 13.dp),
                )
            }
        }
    }
}
