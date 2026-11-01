package com.kacyraho.lightnovel.data.local

import android.content.Context
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.db.SupportSQLiteOpenHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class MigrationTest {
    @Test
    fun migration1To2AddsAnchorColumnsAndUniqueIndex() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val helper = FrameworkSQLiteOpenHelperFactory().create(
            SupportSQLiteOpenHelper.Configuration.builder(context)
                .name(null)
                .callback(
                    object : SupportSQLiteOpenHelper.Callback(1) {
                        override fun onCreate(db: SupportSQLiteDatabase) {
                            db.execSQL(
                                "CREATE TABLE books (" +
                                    "id TEXT NOT NULL PRIMARY KEY, " +
                                    "storage_dir TEXT NOT NULL, slug TEXT, source TEXT NOT NULL, " +
                                    "source_id TEXT NOT NULL, title TEXT NOT NULL, title_zh TEXT, " +
                                    "author TEXT, tags_json TEXT, genre TEXT, " +
                                    "episodes INTEGER NOT NULL, local INTEGER NOT NULL, " +
                                    "created_at TEXT, legacy_json TEXT)",
                            )
                            db.execSQL(
                                "CREATE TABLE read_state (" +
                                    "book_id TEXT NOT NULL PRIMARY KEY, shelf TEXT, " +
                                    "favorite INTEGER NOT NULL, hidden INTEGER NOT NULL, " +
                                    "progress_idx INTEGER NOT NULL, opened_at TEXT, finished_at TEXT)",
                            )
                            db.execSQL(
                                "CREATE UNIQUE INDEX index_books_slug ON books(slug)",
                            )
                            db.execSQL(
                                "INSERT INTO books VALUES (" +
                                    "'b1','b1','slug1','kakuyomu','1','Title',NULL,NULL,NULL,NULL,0,0,NULL,NULL)",
                            )
                            db.execSQL(
                                "INSERT INTO read_state VALUES ('b1','reading',0,0,3,NULL,NULL)",
                            )
                        }

                        override fun onUpgrade(
                            db: SupportSQLiteDatabase,
                            oldVersion: Int,
                            newVersion: Int,
                        ) = Unit
                    },
                )
                .build(),
        )

        val db = helper.writableDatabase
        LightnovelDatabase.MIGRATION_1_2.migrate(db)

        val columns = mutableSetOf<String>()
        db.query("PRAGMA table_info(read_state)").use { cursor ->
            val name = cursor.getColumnIndexOrThrow("name")
            while (cursor.moveToNext()) columns += cursor.getString(name)
        }
        assertTrue(columns.containsAll(setOf("progress_block", "progress_char", "updated_at")))

        val indexes = mutableSetOf<String>()
        db.query("PRAGMA index_list(books)").use { cursor ->
            val name = cursor.getColumnIndexOrThrow("name")
            while (cursor.moveToNext()) indexes += cursor.getString(name)
        }
        assertTrue(indexes.contains("index_books_source_source_id"))

        db.query(
            "SELECT progress_block, progress_char, updated_at FROM read_state WHERE book_id='b1'",
        ).use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals(0, cursor.getInt(0))
            assertEquals(0, cursor.getInt(1))
            assertNull(cursor.getString(2))
        }
        db.close()
    }
}
