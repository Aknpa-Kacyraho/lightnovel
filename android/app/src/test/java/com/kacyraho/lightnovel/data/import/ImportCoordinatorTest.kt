package com.kacyraho.lightnovel.data.import

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.fixture.SyntheticBackup
import java.nio.file.Files
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ImportCoordinatorTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun importsBackupWithTransactionAndCleansStaging() = runTest {
        val zip = tmp.newFile("nineteen.zip").toPath()
        SyntheticBackup.nineteenBooks(zip)

        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val store = FileContentStore(tmp.newFolder("data").toPath())
            val coordinator = ImportCoordinator(db, store)

            val result = coordinator.import(zip)

            assertEquals(19, result.applied.books)
            assertEquals(19, result.applied.chapters)
            assertEquals(19, result.applied.readStates)
            assertEquals(19, db.libraryDao().bookCount())
            assertEquals(19, db.libraryDao().chapterCount())
            assertTrue(
                Files.isRegularFile(
                    store.paths("kakuyomu-1").zh(1),
                ),
            )
            assertTrue(
                Files.isRegularFile(
                    store.root.resolve("legacy/backup-test/data/library.json"),
                ),
            )
            assertFalse(
                Files.list(store.root).use { stream ->
                    stream.anyMatch { it.fileName.toString().startsWith("staging-") }
                },
            )

            val again = coordinator.import(zip)
            assertEquals(19, again.applied.books)
            assertEquals(19, db.libraryDao().bookCount())
        } finally {
            db.close()
        }
    }
}
