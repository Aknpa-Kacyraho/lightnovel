package com.kacyraho.lightnovel.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.ui.theme.lnColors

enum class LnTagKind {
    TYPE,
    KEYWORD,
    SOURCE,
}

enum class StatusTone {
    SUCCESS,
    WARNING,
    ERROR,
    INFO,
    NEUTRAL,
}

@Composable
fun BrandFilterChip(
    selected: Boolean,
    onClick: () -> Unit,
    label: @Composable () -> Unit,
) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = label,
        shape = RoundedCornerShape(9.dp),
        colors = FilterChipDefaults.filterChipColors(
            selectedContainerColor = MaterialTheme.colorScheme.primaryContainer,
            selectedLabelColor = MaterialTheme.colorScheme.onPrimaryContainer,
            selectedLeadingIconColor = MaterialTheme.colorScheme.onPrimaryContainer,
        ),
    )
}

@Composable
fun LnTag(
    text: String,
    modifier: Modifier = Modifier,
    kind: LnTagKind = LnTagKind.KEYWORD,
    onClick: (() -> Unit)? = null,
) {
    val extended = lnColors()
    val container = when (kind) {
        LnTagKind.TYPE -> extended.tagTypeContainer
        LnTagKind.KEYWORD -> extended.tagKeywordContainer
        LnTagKind.SOURCE -> extended.tagSourceContainer
    }
    val content = when (kind) {
        LnTagKind.TYPE -> extended.tagTypeContent
        LnTagKind.KEYWORD -> extended.tagKeywordContent
        LnTagKind.SOURCE -> extended.tagSourceContent
    }
    val border = when (kind) {
        LnTagKind.TYPE -> null
        LnTagKind.KEYWORD -> BorderStroke(
            1.dp,
            MaterialTheme.colorScheme.outline.copy(alpha = 0.45f),
        )
        LnTagKind.SOURCE -> BorderStroke(
            1.dp,
            MaterialTheme.colorScheme.outline.copy(alpha = 0.55f),
        )
    }
    val clickModifier = if (onClick == null) {
        Modifier
    } else {
        Modifier
            .minimumInteractiveComponentSize()
            .clickable(onClick = onClick)
    }
    Surface(
        modifier = modifier.then(clickModifier),
        shape = RoundedCornerShape(if (kind == LnTagKind.SOURCE) 50 else 8),
        color = container,
        contentColor = content,
        border = border,
        tonalElevation = 0.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = text,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = if (kind == LnTagKind.TYPE) FontWeight.SemiBold else FontWeight.Normal,
            )
        }
    }
}

@Composable
fun StatusBadge(
    text: String,
    tone: StatusTone,
    modifier: Modifier = Modifier,
) {
    val extended = lnColors()
    val color: Color = when (tone) {
        StatusTone.SUCCESS -> extended.success
        StatusTone.WARNING -> extended.warning
        StatusTone.ERROR -> MaterialTheme.colorScheme.error
        StatusTone.INFO -> extended.info
        StatusTone.NEUTRAL -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(6.dp),
        color = color.copy(alpha = 0.12f),
        contentColor = color,
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp),
            style = MaterialTheme.typography.labelSmall,
        )
    }
}

@Composable
fun SourceBadge(label: String, modifier: Modifier = Modifier) {
    LnTag(text = label, kind = LnTagKind.SOURCE, modifier = modifier)
}
