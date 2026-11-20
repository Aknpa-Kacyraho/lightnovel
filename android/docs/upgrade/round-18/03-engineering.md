# Round 18 · 工程师视角升级指南（v1.6.2）

> 基线：1.6.1 / versionCode 54。本轮是三个小修复：取消保护、状态合并、去重。
> 每项都要能说清「为什么原来的实现不够」。

## 1. 工程问题与方案

### E1. 最后进度可能被取消（P1）

`onPageChanged`：

```kotlin
saveJob?.cancel()
saveJob = viewModelScope.launch { repository.updateProgress(bookId, anchor) }
```

ViewModel 清空时 `viewModelScope` 取消，`saveJob` 也取消；若协程尚未执行到
Room suspend，写入丢失。

**方案**：

```kotlin
saveJob = viewModelScope.launch(start = CoroutineStart.UNDISPATCHED) {
    withContext(NonCancellable) {
        repository.updateProgress(bookId, anchor)
    }
}
```

- `UNDISPATCHED`：立即在当前线程执行到第一个挂起点，不会因为排队被取消；
- `NonCancellable`：进入 Room 写入后不被取消打断；
- 仍先 `saveJob?.cancel()`，避免连续翻页堆积。

同样的保护用于 `onScrollParagraphChanged` 的写入。

**测试**：无法在 JVM 稳定模拟 scope 取消；依靠代码审查与真机。

### E2. 书架筛选一次更新（P2）

`LibraryScreen` 的书架下拉调用：

```kotlin
onShelfChange(value)
onFavoritesOnlyChange(false)
onRemovedOnlyChange(false)
```

三次 `filter.value.copy` → 三次 `flatMapLatest` 重建。

**方案**：ViewModel 增加

```kotlin
fun applyShelfFilter(shelf: String?) {
    filter.value = filter.value.copy(
        shelf = shelf,
        favoritesOnly = false,
        removedOnly = false,
    )
}
```

UI 只调用一次；保留原 `setShelf/setFavoritesOnly/setRemovedOnly` 供其他入口。
空态的「清除筛选」也改成 `applyShelfFilter(null)` + query 清空？保持现有三次调用
（它需要清 query/shelf/favorites/removed 四项，可用一个新方法，但不在本轮）。

### E3. 书名翻译去重（P2）

`MetadataTranslationService.translateTitles` 不检查 `cardCache`，也不防并发。

**方案**：

- 加 `private val titleMutex = Mutex()`；
- `translateTitles` 开头 `if (!titleMutex.tryLock()) return emptyMap()`，`finally { unlock }`；
- 过滤 `cardCache[cacheKey]?.titleZh` 已有值的书；
- 成功后写入 `cardCache`（现有代码已写 store，补内存缓存）。

**测试**：`MetadataTranslationServiceTest` 可加「已有缓存不请求」用例（需要 fake client）。

### E4. 版本与文档

- `versionCode = 55`，`versionName = "1.6.2"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. 进度写入的 `UNDISPATCHED + NonCancellable`。
2. `applyShelfFilter` + UI 接入。
3. 标题翻译去重。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥270，0 failures；lint 0 errors，warning ≤22；APK versionCode 55。

## 4. 风险

- `NonCancellable` 写入会在退出后继续几毫秒；Room 写入快，可接受。
- `tryLock` 让并发请求直接返回空 map，调用方需容忍「这次没翻」；下次进入会重试。
- `applyShelfFilter` 与旧 setter 并存，注意 UI 不要同时调用两套。
