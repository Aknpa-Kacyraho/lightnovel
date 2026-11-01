package com.kacyraho.lightnovel

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivityTest {
    private val composeRule = createAndroidComposeRule<MainActivity>()

    @get:Rule
    val rules: RuleChain = RuleChain
        .outerRule(SkipOnMiuiRule())
        .around(composeRule)

    @Test
    fun showsAppTitle() {
        composeRule.onNodeWithText("Ka小说家").fetchSemanticsNode()
    }
}
