package com.kacyraho.lightnovel.data.online

class NoveliaAccountService(
    private val client: NoveliaClient,
    private val onlineBookService: OnlineBookService,
    private val sessionStore: NoveliaSessionStore,
) {
    init {
        client.setToken(sessionStore.load())
    }

    fun isLoggedIn(): Boolean = client.hasToken()

    suspend fun login(username: String, password: String) {
        require(username.isNotBlank() && password.isNotBlank()) { "账号和密码不能为空" }
        val token = client.login(authBaseUrl(), username.trim(), password)
        client.setToken(token)
        sessionStore.save(token)
    }

    fun logout() {
        client.setToken(null)
        sessionStore.clear()
    }

    suspend fun importFavorites(limit: Int = 20): NoveliaImportResult {
        if (!isLoggedIn()) error("请先登录")
        val favored = client.favored()
        val folder = favored.favoredWeb.firstOrNull { it.id == "default" }
            ?: favored.favoredWeb.firstOrNull()
            ?: return NoveliaImportResult(folders = 0, message = "云端没有收藏夹")
        val page = client.favoredWeb(folder.id, pageSize = limit)
        var books = 0
        var skipped = 0
        for (item in page.items.take(limit)) {
            runCatching { onlineBookService.addToShelf(item) }
                .onSuccess { books++ }
                .onFailure { skipped++ }
        }
        return NoveliaImportResult(
            folders = favored.favoredWeb.size,
            books = books,
            skipped = skipped,
            message = "收藏夹「${folder.title.ifBlank { folder.id }}」已导入 $books 本",
        )
    }

    suspend fun importHistory(limit: Int = 20): NoveliaImportResult {
        if (!isLoggedIn()) error("请先登录")
        val page = client.readHistory(pageSize = limit)
        var books = 0
        var skipped = 0
        for (item in page.items.take(limit)) {
            runCatching { onlineBookService.addToShelf(item) }
                .onSuccess { books++ }
                .onFailure { skipped++ }
        }
        return NoveliaImportResult(
            history = books,
            skipped = skipped,
            message = "阅读历史已导入 $books 本",
        )
    }

    private fun authBaseUrl(): String =
        if (client.baseUrl.contains("book.xkvi.top")) {
            "https://book.xkvi.top/api/v1/auth"
        } else {
            "https://auth.novelia.cc/api/v1/auth"
        }
}
