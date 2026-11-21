package com.kacyraho.lightnovel.data.export

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BackupPathFilterTest {
    @Test
    fun excludesBackupDirectories() {
        assertFalse(isExportableRelativePath("book.bak-20260101-120000/raw/0001.txt"))
    }

    @Test
    fun excludesCacheDirectories() {
        assertFalse(isExportableRelativePath("book/cache/translation/1/abc.json"))
    }

    @Test
    fun excludesTemporaryFiles() {
        assertFalse(isExportableRelativePath("book/raw/0001.txt.tmp-123"))
        assertFalse(isExportableRelativePath("book/raw/0001.txt.part"))
        assertFalse(isExportableRelativePath("book/raw/0001.txt.restore-tmp"))
    }

    @Test
    fun keepsNormalBookFiles() {
        assertTrue(isExportableRelativePath("book/raw/0001.txt"))
        assertTrue(isExportableRelativePath("book/chapters/0001.meta.json"))
        assertTrue(isExportableRelativePath("book/story.json"))
    }
}
