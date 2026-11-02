package com.kacyraho.lightnovel.data.local

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface CatalogDao {
    @Upsert
    suspend fun upsert(books: List<CatalogBookEntity>)

    @Query("SELECT * FROM catalog_books ORDER BY last_seen_at DESC")
    fun observeAll(): Flow<List<CatalogBookEntity>>

    @Query(
        """
        SELECT * FROM catalog_books
        WHERE provider = :provider AND source_id IN (:sourceIds)
        """,
    )
    suspend fun books(provider: String, sourceIds: List<String>): List<CatalogBookEntity>

    @Query("SELECT COUNT(*) FROM catalog_books")
    suspend fun count(): Int

    @Query("SELECT * FROM catalog_books ORDER BY RANDOM() LIMIT :limit")
    suspend fun random(limit: Int): List<CatalogBookEntity>
}
