package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.data.local.BookmarkEntity
import com.kacyraho.lightnovel.reader.engine.ReaderTheme

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BookmarkSheet(
    bookmarks: List<BookmarkEntity>,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onJump: (BookmarkEntity) -> Unit,
    onDelete: (BookmarkEntity) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
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
            Text("书签", style = MaterialTheme.typography.titleMedium, color = theme.text)
            if (bookmarks.isEmpty()) {
                Text(
                    "还没有书签；阅读时点「更多 → 添加书签」。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = theme.secondary,
                    modifier = Modifier.padding(vertical = 24.dp),
                )
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 440.dp),
                ) {
                    items(
                        bookmarks,
                        key = { "${it.bookId}/${it.chapterIdx}/${it.paragraphId}" },
                    ) { bookmark ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onJump(bookmark) }
                                .padding(vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    "第 ${bookmark.chapterIdx} 话",
                                    style = MaterialTheme.typography.titleSmall,
                                    color = theme.text,
                                )
                                Text(
                                    bookmark.preview,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = theme.secondary,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Text(
                                    relativeTime(bookmark.createdAt),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = theme.secondary,
                                )
                            }
                            TextButton(onClick = { onDelete(bookmark) }) {
                                Text("删除", color = theme.danger)
                            }
                        }
                    }
                }
            }
        }
    }
}
