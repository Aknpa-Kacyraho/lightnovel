package com.kacyraho.lightnovel.reader

import android.annotation.SuppressLint
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun ReaderScreen(
    title: String,
    subtitle: String,
    text: String,
    modifier: Modifier = Modifier,
) {
    var fontSizeSp by rememberSaveable { mutableStateOf(18f) }
    val density = LocalDensity.current
    val textColor = MaterialTheme.colorScheme.onBackground

    Column(
        modifier = modifier
            .fillMaxSize()
            .statusBarsPadding()
            .navigationBarsPadding()
            .testTag("reader-screen"),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = title, style = MaterialTheme.typography.titleMedium)
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(
                onClick = { fontSizeSp = (fontSizeSp - 1f).coerceAtLeast(12f) },
            ) {
                Text("A-")
            }
            Text(
                text = fontSizeSp.toInt().toString(),
                style = MaterialTheme.typography.bodySmall,
            )
            TextButton(
                onClick = { fontSizeSp = (fontSizeSp + 1f).coerceAtMost(28f) },
            ) {
                Text("A+")
            }
        }

        BoxWithConstraints(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        ) {
            val widthPx = with(density) {
                (maxWidth - 32.dp).roundToPx().coerceAtLeast(1)
            }
            val heightPx = with(density) {
                maxHeight.roundToPx().coerceAtLeast(1)
            }
            val paint = remember(fontSizeSp, textColor, density) {
                TextPaint().apply {
                    textSize = with(density) { fontSizeSp.sp.toPx() }
                    typeface = Typeface.SERIF
                    isAntiAlias = true
                    color = textColor.toArgb()
                }
            }
            val layout = remember(text, widthPx, paint) {
                buildReaderLayout(text, widthPx, paint)
            }
            val pages = remember(layout, heightPx) {
                StaticLayoutPaginator.paginate(layout, heightPx)
            }
            val pagerState = rememberPagerState(
                pageCount = { pages.pages.size.coerceAtLeast(1) },
            )

            LaunchedEffect(pages.pages.size) {
                if (pagerState.currentPage >= pages.pages.size) {
                    pagerState.scrollToPage(0)
                }
            }

            HorizontalPager(
                state = pagerState,
                modifier = Modifier
                    .fillMaxSize()
                    .testTag("reader-pager"),
            ) { index ->
                val page = pages.pages.getOrNull(index) ?: pages.pages.first()
                AndroidView(
                    factory = { context -> ReaderPageView(context) },
                    update = { view -> view.bind(layout, page) },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                )
            }

            Text(
                text = "${pagerState.currentPage + 1}/${pages.pages.size}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(8.dp),
            )
        }
    }
}

@SuppressLint("WrongConstant")
private fun buildReaderLayout(
    text: String,
    widthPx: Int,
    paint: TextPaint,
): StaticLayout = StaticLayout.Builder
    .obtain(text, 0, text.length, paint, widthPx)
    .setAlignment(Layout.Alignment.ALIGN_NORMAL)
    .setLineSpacing(0f, 1.4f)
    .setIncludePad(false)
    .setBreakStrategy(Layout.BREAK_STRATEGY_SIMPLE)
    .setHyphenationFrequency(Layout.HYPHENATION_FREQUENCY_NONE)
    .build()


