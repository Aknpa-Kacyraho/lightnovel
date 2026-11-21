package com.kacyraho.lightnovel.data.story

import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class StoryMemoryGlossaryRevisionTest {
    @Test
    fun glossaryChangesRevision() {
        val base = StoryMemory(glossary = listOf(entry("勇者", "勇者")))
        val changed = base.copy(glossary = listOf(entry("勇者", "英雄")))

        assertNotEquals(
            StoryMemoryStore.glossaryRevision(base),
            StoryMemoryStore.glossaryRevision(changed),
        )
    }

    @Test
    fun charactersSummariesAndStyleDoNotChangeGlossaryRevision() {
        val base = StoryMemory(glossary = listOf(entry("勇者", "勇者")))
        val expanded = base.copy(
            characters = listOf(CharacterCard(source = "勇者", target = "勇者")),
            summaries = mapOf(1 to ChapterSummary(index = 1, text = "摘要")),
            style = StoryStyle(general = "轻松"),
            lessons = listOf("保持短句"),
        )

        assertEquals(
            StoryMemoryStore.glossaryRevision(base),
            StoryMemoryStore.glossaryRevision(expanded),
        )
    }

    @Test
    fun emptyGlossaryReturnsBlank() {
        assertEquals("", StoryMemoryStore.glossaryRevision(StoryMemory()))
    }

    private fun entry(source: String, target: String) = GlossaryEntry(
        id = source,
        source = source,
        target = target,
        aliases = emptyList(),
    )
}
