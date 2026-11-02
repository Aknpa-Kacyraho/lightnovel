package com.kacyraho.lightnovel.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        BookEntity::class,
        CatalogBookEntity::class,
        ReadStateEntity::class,
        AliasEntity::class,
        ChapterEntity::class,
    ],
    version = 3,
    exportSchema = true,
)
abstract class LightnovelDatabase : RoomDatabase() {
    abstract fun libraryDao(): LibraryDao

    abstract fun catalogDao(): CatalogDao

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

        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS catalog_books (" +
                        "provider TEXT NOT NULL, " +
                        "source_id TEXT NOT NULL, " +
                        "title TEXT NOT NULL, " +
                        "author TEXT, " +
                        "tags_json TEXT, " +
                        "episodes INTEGER NOT NULL, " +
                        "url TEXT, " +
                        "synopsis TEXT, " +
                        "updated_at TEXT, " +
                        "status TEXT, " +
                        "characters INTEGER, " +
                        "genre TEXT, " +
                        "title_zh TEXT, " +
                        "synopsis_zh TEXT, " +
                        "tags_zh_json TEXT, " +
                        "first_seen_at TEXT NOT NULL, " +
                        "last_seen_at TEXT NOT NULL, " +
                        "PRIMARY KEY(provider, source_id))",
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_catalog_books_last_seen_at " +
                        "ON catalog_books(last_seen_at)",
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_catalog_books_updated_at " +
                        "ON catalog_books(updated_at)",
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_catalog_books_title " +
                        "ON catalog_books(title)",
                )
            }
        }
    }
}
