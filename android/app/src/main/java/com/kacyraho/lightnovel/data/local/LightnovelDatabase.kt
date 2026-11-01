package com.kacyraho.lightnovel.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        BookEntity::class,
        ReadStateEntity::class,
        AliasEntity::class,
        ChapterEntity::class,
    ],
    version = 2,
    exportSchema = true,
)
abstract class LightnovelDatabase : RoomDatabase() {
    abstract fun libraryDao(): LibraryDao

    companion object {
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "ALTER TABLE read_state ADD COLUMN progress_block INTEGER NOT NULL DEFAULT 0",
                )
                db.execSQL(
                    "ALTER TABLE read_state ADD COLUMN progress_char INTEGER NOT NULL DEFAULT 0",
                )
                db.execSQL("ALTER TABLE read_state ADD COLUMN updated_at TEXT")
                db.execSQL(
                    "CREATE UNIQUE INDEX IF NOT EXISTS " +
                        "index_books_source_source_id ON books(source, source_id)",
                )
            }
        }
    }
}
