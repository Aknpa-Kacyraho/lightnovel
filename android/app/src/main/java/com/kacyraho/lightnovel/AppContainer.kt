package com.kacyraho.lightnovel

import android.content.Context
import androidx.room.Room
import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.KeystoreApiKeyStore
import com.kacyraho.lightnovel.core.settings.SearchHistoryStore
import com.kacyraho.lightnovel.core.settings.SearchPresetStore
import com.kacyraho.lightnovel.core.settings.TaskIgnoreStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.CacheManager
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.core.storage.SafStager
import com.kacyraho.lightnovel.data.catalog.CatalogRepository
import com.kacyraho.lightnovel.data.glossary.GlossaryStore
import com.kacyraho.lightnovel.data.knowledge.KnowledgeExtractionService
import com.kacyraho.lightnovel.data.knowledge.KnowledgeQueryService
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.worldline.BranchKnowledgeExtractor
import com.kacyraho.lightnovel.data.worldline.WorldlineService
import com.kacyraho.lightnovel.data.worldline.WorldlineStore
import com.kacyraho.lightnovel.data.story.StoryMemoryService
import com.kacyraho.lightnovel.data.story.StoryMemoryStore
import com.kacyraho.lightnovel.data.translation.MetadataTranslationService
import com.kacyraho.lightnovel.data.translation.TranslationTaskRegistry
import com.kacyraho.lightnovel.data.translation.TranslationService
import com.kacyraho.lightnovel.data.translation.TranslationVersionStore
import com.kacyraho.lightnovel.data.download.BookDownloadScheduler
import com.kacyraho.lightnovel.data.export.BackupExporter
import com.kacyraho.lightnovel.data.export.EpubExporter
import com.kacyraho.lightnovel.data.import.ImportCoordinator
import com.kacyraho.lightnovel.data.import.LocalDocumentImporter
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.online.KeystoreNoveliaSessionStore
import com.kacyraho.lightnovel.data.online.NoveliaAccountService
import com.kacyraho.lightnovel.data.online.NoveliaClient
import com.kacyraho.lightnovel.data.online.OnlineBookService
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.repository.RoomLibraryRepository
import com.kacyraho.lightnovel.data.source.DirectLibraryService
import com.kacyraho.lightnovel.data.source.KakuyomuSource
import com.kacyraho.lightnovel.data.source.SyosetuSource
import com.kacyraho.lightnovel.reader.engine.ReaderChapterCache
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

class AppContainer(
    context: Context,
) {
    val dataRoot: Path = Paths.get(context.filesDir.absolutePath, "lightnovel-data").also {
        Files.createDirectories(it.resolve("novels"))
        Files.createDirectories(it.resolve("legacy"))
    }

    val database: LightnovelDatabase = Room.databaseBuilder(
        context,
        LightnovelDatabase::class.java,
        "lightnovel.db",
    )
        .addMigrations(
            LightnovelDatabase.MIGRATION_1_2,
            LightnovelDatabase.MIGRATION_2_3,
        )
        .build()

    val contentStore: ContentStore = FileContentStore(dataRoot)

    val cacheManager: CacheManager = CacheManager(contentStore)

    val safStager: SafStager = SafStager(context)

    val libraryRepository: LibraryRepository = RoomLibraryRepository(database)

    val catalogRepository: CatalogRepository = CatalogRepository(database.catalogDao())

    val readerChapterCache: ReaderChapterCache = ReaderChapterCache()

    val directLibraryService: DirectLibraryService = DirectLibraryService(
        sources = listOf(KakuyomuSource(), SyosetuSource()),
        dao = database.libraryDao(),
        database = database,
        contentStore = contentStore,
    )

    val noveliaClient: NoveliaClient = NoveliaClient()

    val onlineBookService: OnlineBookService = OnlineBookService(
        client = noveliaClient,
        dao = database.libraryDao(),
        contentStore = contentStore,
    )

    val noveliaAccountService: NoveliaAccountService = NoveliaAccountService(
        client = noveliaClient,
        onlineBookService = onlineBookService,
        sessionStore = KeystoreNoveliaSessionStore(context),
    )

    val backupExporter: BackupExporter = BackupExporter(dataRoot, database.libraryDao())

    val epubExporter: EpubExporter = EpubExporter(database.libraryDao(), contentStore)

    val settingsStore: SettingsStore = SettingsStore(context)

    val searchHistoryStore: SearchHistoryStore = SearchHistoryStore(context)

    val searchPresetStore: SearchPresetStore = SearchPresetStore(context)

    val taskIgnoreStore: TaskIgnoreStore = TaskIgnoreStore(context)

    val apiKeyStore: ApiKeyStore = KeystoreApiKeyStore(context)

    val glossaryStore: GlossaryStore = GlossaryStore(dataRoot)

    val storyMemoryStore: StoryMemoryStore = StoryMemoryStore(contentStore)

    val storyMemoryService: StoryMemoryService = StoryMemoryService(
        contentStore = contentStore,
        storyStore = storyMemoryStore,
        settingsStore = settingsStore,
        apiKeyStore = apiKeyStore,
    )

    val knowledgeStore: KnowledgeStore = KnowledgeStore(contentStore)

    val knowledgeExtractionService: KnowledgeExtractionService = KnowledgeExtractionService(
        contentStore = contentStore,
        knowledgeStore = knowledgeStore,
        settingsStore = settingsStore,
        apiKeyStore = apiKeyStore,
        storyMemoryStore = storyMemoryStore,
    )

    val knowledgeQueryService: KnowledgeQueryService = KnowledgeQueryService(knowledgeStore)

    val worldlineStore: WorldlineStore = WorldlineStore(contentStore)

    val branchKnowledgeExtractor: BranchKnowledgeExtractor = BranchKnowledgeExtractor(
        worldlineStore = worldlineStore,
        knowledgeStore = knowledgeStore,
        settingsStore = settingsStore,
        apiKeyStore = apiKeyStore,
    )

    val worldlineService: WorldlineService = WorldlineService(
        contentStore = contentStore,
        knowledgeStore = knowledgeStore,
        storyMemoryStore = storyMemoryStore,
        worldlineStore = worldlineStore,
        branchKnowledgeExtractor = branchKnowledgeExtractor,
        settingsStore = settingsStore,
        apiKeyStore = apiKeyStore,
    )

    val versionStore: TranslationVersionStore = TranslationVersionStore(contentStore)

    val metadataTranslationService: MetadataTranslationService = MetadataTranslationService(
        contentStore = contentStore,
        dao = database.libraryDao(),
        settingsStore = settingsStore,
        apiKeyStore = apiKeyStore,
    )

    val translationTaskRegistry: TranslationTaskRegistry = TranslationTaskRegistry()

    val translationService: TranslationService = TranslationService(
        contentStore = contentStore,
        dao = database.libraryDao(),
        settingsStore = settingsStore,
        apiKeyStore = apiKeyStore,
        storyMemoryStore = storyMemoryStore,
        versionStore = versionStore,
    )

    val importCoordinator: ImportCoordinator = ImportCoordinator(
        database = database,
        contentStore = contentStore,
    )

    val localDocumentImporter: LocalDocumentImporter = LocalDocumentImporter(
        database = database,
        contentStore = contentStore,
    )

    val bookDownloadScheduler: BookDownloadScheduler by lazy {
        BookDownloadScheduler(context)
    }
}
