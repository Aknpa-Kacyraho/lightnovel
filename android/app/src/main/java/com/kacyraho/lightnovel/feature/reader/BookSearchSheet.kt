package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.reader.engine.ReaderTheme
import kotlinx.coroutines.delay

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BookSearchSheet(
    results: List<BookSearchHit>,
    searching: Boolean,
    scope: String,
    theme: ReaderTheme,
    onSearch: (String) -> Unit,
    onDismiss: () -> Unit,
    onJump: (BookSearchHit) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var query by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(query) {
        delay(300)
        onSearch(query)
    }

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
                .padding(horizontal = 16.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("搜索本书", style = MaterialTheme.typography.titleMedium, color = theme.text)
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("输入关键词") },
                singleLine = true,
                colors = readerOutlinedFieldColors(theme),
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                "搜索范围：$scope · 最多 30 条",
                style = MaterialTheme.typography.labelSmall,
                color = theme.secondary,
            )
            if (searching) {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth(),
                    color = theme.text.copy(alpha = 0.45f),
                    trackColor = theme.secondary.copy(alpha = 0.15f),
                )
            }
            when {
                query.isBlank() -> Text(
                    "输入关键词，搜索当前书的正文。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = theme.secondary,
                    modifier = Modifier.padding(vertical = 16.dp),
                )

                results.isEmpty() && !searching -> Text(
                    "没有找到；换个关键词试试。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = theme.secondary,
                    modifier = Modifier.padding(vertical = 16.dp),
                )

                else -> LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 420.dp),
                ) {
                    items(results) { hit ->
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onJump(hit) }
                                .padding(vertical = 8.dp),
                            verticalArrangement = Arrangement.spacedBy(2.dp),
                        ) {
                            Text(
                                "第 ${hit.chapterIndex} 话 · ${hit.chapterTitle}",
                                style = MaterialTheme.typography.titleSmall,
                                color = theme.text,
                            )
                            Text(
                                buildAnnotatedString {
                                    append(hit.before)
                                    withStyle(
                                        SpanStyle(
                                            color = theme.text,
                                            fontWeight = FontWeight.Bold,
                                        ),
                                    ) {
                                        append(hit.match)
                                    }
                                    append(hit.after)
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = theme.secondary,
                            )
                        }
                    }
                }
            }
        }
    }
}
