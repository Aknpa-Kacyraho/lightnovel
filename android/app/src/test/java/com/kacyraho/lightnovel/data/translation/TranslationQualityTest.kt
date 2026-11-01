package com.kacyraho.lightnovel.data.translation

import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TranslationQualityTest {
    @Test
    fun acceptsNormalTranslation() {
        val source = "「おはよう」"
        assertNull(TranslationValidators.paragraphIssue(source, "「早上好」"))
    }

    @Test
    fun rejectsDroppedDialogueQuote() {
        val issue = TranslationValidators.paragraphIssue("「おはよう」", "早上好")
        assertTrue(issue != null && issue.contains("引号"))
    }

    @Test
    fun rejectsSeverelyShortTranslation() {
        val source = "これはとても長い日本語の文章です。".repeat(4)
        val issue = TranslationValidators.paragraphIssue(source, "很短")
        assertTrue(issue != null && issue.contains("长度"))
    }

    @Test
    fun detectsSingleDroppedDialogue() {
        assertTrue(TranslationValidators.missingDialogue("「おはよう」", "早上好"))
    }
}
