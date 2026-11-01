package com.kacyraho.lightnovel.data.local

import androidx.room.ColumnInfo
import androidx.room.Embedded
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.Relation

@Entity(
    tableName = "books",
    indices = [
        Index(value = ["slug"], unique = true),
        Index(value = ["source", "source_id"], unique = true),
    ],
)
data class BookEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "storage_dir") val storageDir: String,
    val slug: String?,
    val source: String,
    @ColumnInfo(name = "source_id") val sourceId: String,
    val title: String,
    @ColumnInfo(name = "title_zh") val titleZh: String?,
    val author: String?,
    @ColumnInfo(name = "tags_json") val tagsJson: String?,
    val genre: String?,
    val episodes: Int,
    val local: Boolean,
    @ColumnInfo(name = "created_at") val createdAt: String?,
    @ColumnInfo(name = "legacy_json") val legacyJson: String?,
)

@Entity(tableName = "read_state")
data class ReadStateEntity(
    @PrimaryKey @ColumnInfo(name = "book_id") val bookId: String,
    val shelf: String?,
    val favorite: Boolean,
    val hidden: Boolean,
    @ColumnInfo(name = "progress_idx") val progressIdx: Int,
    @ColumnInfo(name = "progress_block") val progressBlock: Int = 0,
    @ColumnInfo(name = "progress_char") val progressChar: Int = 0,
    @ColumnInfo(name = "opened_at") val openedAt: String?,
    @ColumnInfo(name = "finished_at") val finishedAt: String?,
    @ColumnInfo(name = "updated_at") val updatedAt: String? = null,
)

data class ChapterTaskRow(
    @ColumnInfo(name = "book_id") val bookId: String,
    val idx: Int,
    @ColumnInfo(name = "chapter_title") val chapterTitle: String?,
    @ColumnInfo(name = "chapter_title_zh") val chapterTitleZh: String?,
    val status: String?,
    @ColumnInfo(name = "book_title") val bookTitle: String,
    @ColumnInfo(name = "book_title_zh") val bookTitleZh: String?,
    @ColumnInfo(name = "updated_at") val updatedAt: String?,
)

data class BookWithState(
    @Embedded val book: BookEntity,
    @Relation(parentColumn = "id", entityColumn = "book_id")
    val state: ReadStateEntity?,
)

@Entity(tableName = "aliases")
data class AliasEntity(
    @PrimaryKey @ColumnInfo(name = "old_slug") val oldSlug: String,
    @ColumnInfo(name = "final_slug") val finalSlug: String,
)

@Entity(
    tableName = "chapters",
    primaryKeys = ["book_id", "idx"],
)
data class ChapterEntity(
    @ColumnInfo(name = "book_id") val bookId: String,
    val idx: Int,
    val title: String?,
    @ColumnInfo(name = "title_zh") val titleZh: String?,
    @ColumnInfo(name = "raw_path") val rawPath: String?,
    @ColumnInfo(name = "zh_path") val zhPath: String?,
    val status: String?,
    @ColumnInfo(name = "token_in") val tokenIn: Int,
    @ColumnInfo(name = "token_out") val tokenOut: Int,
    val model: String?,
    @ColumnInfo(name = "updated_at") val updatedAt: String?,
)
