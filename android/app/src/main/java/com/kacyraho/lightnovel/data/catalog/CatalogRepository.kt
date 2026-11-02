package com.kacyraho.lightnovel.data.catalog

import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.CatalogBookEntity
import com.kacyraho.lightnovel.data.local.CatalogDao
import com.kacyraho.lightnovel.data.source.SourceBook
import java.time.Instant
import kotlinx.coroutines.flow.Flow

class CatalogRepository(
    private val dao: CatalogDao,
) {
    fun observeAll(): Flow<List<CatalogBookEntity>> = dao.observeAll()

    suspend fun count(): Int = dao.count()

    suspend fun random(limit: Int): List<SourceBook> =
        dao.random(limit.coerceAtLeast(1)).map { it.toSourceBook() }

    suspend fun remember(books: List<SourceBook>): Int {
        val unique = books
            .filter { it.provider.isNotBlank() && it.id.isNotBlank() }
            .distinctBy { it.provider to it.id }
        if (unique.isEmpty()) return 0
        val now = Instant.now().toString()
        val existing = unique.groupBy { it.provider }
            .flatMap { (provider, rows) ->
                dao.books(provider, rows.map { it.id })
            }
            .associateBy { it.provider to it.sourceId }
        val entities = unique.map { book ->
            val old = existing[book.provider to book.id]
            CatalogBookEntity(
                provider = book.provider,
                sourceId = book.id,
                title = book.title.ifBlank { old?.title.orEmpty() },
                author = book.author.takeIf { it.isNotBlank() } ?: old?.author,
                tagsJson = BookTags.encode(book.tags) ?: old?.tagsJson,
                episodes = book.episodes.takeIf { it > 0 } ?: old?.episodes ?: 0,
                url = book.url.takeIf { it.isNotBlank() } ?: old?.url,
                synopsis = book.synopsis.takeIf { it.isNotBlank() } ?: old?.synopsis,
                updatedAt = book.updatedAt.takeIf { it.isNotBlank() } ?: old?.updatedAt,
                status = book.status ?: old?.status,
                characters = book.characters ?: old?.characters,
                genre = book.genre ?: old?.genre,
                titleZh = book.titleZh.takeIf { !it.isNullOrBlank() } ?: old?.titleZh,
                synopsisZh = book.synopsisZh.takeIf { !it.isNullOrBlank() } ?: old?.synopsisZh,
                tagsZhJson = BookTags.encode(book.tagsZh) ?: old?.tagsZhJson,
                firstSeenAt = old?.firstSeenAt ?: now,
                lastSeenAt = now,
            )
        }
        dao.upsert(entities)
        return entities.size
    }
}

fun CatalogBookEntity.tagPairs(): List<Pair<String, String>> {
    val original = BookTags.decode(tagsJson)
    val localized = BookTags.decode(tagsZhJson)
    return if (localized.size == original.size) {
        original.zip(localized).map { (source, zh) ->
            source to (zh.ifBlank { TagLocalizer.translate(source) } ?: source)
        }
    } else {
        original.map { source -> source to (TagLocalizer.translate(source) ?: source) }
    }
}

fun CatalogBookEntity.toSourceBook(): SourceBook = SourceBook(
    provider = provider,
    id = sourceId,
    title = title,
    author = author.orEmpty(),
    tags = BookTags.decode(tagsJson),
    episodes = episodes,
    url = url.orEmpty(),
    synopsis = synopsis.orEmpty(),
    updatedAt = updatedAt.orEmpty(),
    status = status,
    characters = characters,
    genre = genre,
    titleZh = titleZh,
    synopsisZh = synopsisZh,
    tagsZh = BookTags.decode(tagsZhJson),
)

val CatalogBookEntity.key: String
    get() = "$provider/$sourceId"
