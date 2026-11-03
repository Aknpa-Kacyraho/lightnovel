package com.kacyraho.lightnovel.feature.reader

import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import com.kacyraho.lightnovel.reader.engine.ReaderTheme

@Composable
fun readerOutlinedFieldColors(theme: ReaderTheme) = OutlinedTextFieldDefaults.colors(
    focusedTextColor = theme.text,
    unfocusedTextColor = theme.text,
    disabledTextColor = theme.secondary,
    cursorColor = theme.text,
    focusedBorderColor = theme.text.copy(alpha = 0.7f),
    unfocusedBorderColor = theme.secondary.copy(alpha = 0.55f),
    disabledBorderColor = theme.secondary.copy(alpha = 0.35f),
    focusedLabelColor = theme.text,
    unfocusedLabelColor = theme.secondary,
    focusedContainerColor = theme.background,
    unfocusedContainerColor = theme.background,
    disabledContainerColor = theme.background,
    errorTextColor = theme.danger,
    errorBorderColor = theme.danger,
    errorLabelColor = theme.danger,
    errorCursorColor = theme.danger,
)

@Composable
fun readerFieldColors(theme: ReaderTheme) = TextFieldDefaults.colors(
    focusedTextColor = theme.text,
    unfocusedTextColor = theme.text,
    disabledTextColor = theme.secondary,
    cursorColor = theme.text,
    focusedContainerColor = theme.background,
    unfocusedContainerColor = theme.background,
    disabledContainerColor = theme.background,
    errorTextColor = theme.danger,
    errorCursorColor = theme.danger,
)
