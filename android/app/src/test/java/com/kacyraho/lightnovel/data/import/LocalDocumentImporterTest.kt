package com.kacyraho.lightnovel.data.import

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalDocumentImporterTest {
    @Test
    fun zipHeaderIdentifiesRenamedEpub() {
        assertTrue(hasZipHeader(byteArrayOf(0x50, 0x4B, 0x03, 0x04)))
    }

    @Test
    fun plainTextIsNotTreatedAsZip() {
        assertFalse(hasZipHeader("第一章 开始".toByteArray(Charsets.UTF_8)))
    }

    @Test
    fun shortByteArrayIsNotZip() {
        assertFalse(hasZipHeader(byteArrayOf(0x50, 0x4B)))
    }
}
