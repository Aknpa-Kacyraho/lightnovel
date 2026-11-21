# Round 21 · 工程师视角升级指南（v1.7.2）

> 基线：1.7.1 / versionCode 57。本轮拆开「术语版本」与「综合版本」，
> 修过期提示的误报与漏报；不改数据库表结构。

## 1. 工程问题与方案

### E1. 综合 revision 无法区分术语变化（P1）

`StoryMemoryStore.revision(memory)` 把术语、人物、风格、lessons 一起 hash。
`ReaderViewModel.currentGlossaryRevision` 直接用它，`staleReasons` 又用
`sidecar.storyRevision ?: sidecar.glossaryRevision` 与它比较。

结果：每生成一条章节摘要，`memory.revision` 变化 → 所有旧章节都报
`GLOSSARY` 过期。

**方案**：新增纯术语版本：

```kotlin
fun glossaryRevision(memory: StoryMemory): String {
    val glossary = glossaryText(memory) // 与 revision() 内部同一份拼接
    return if (glossary.isBlank()) "" else Hashes.sha256(glossary)
}
```

- `revision(memory)` 的输出保持不变（缓存 key 不受影响）；
- 新增函数只对 `cleanGlossary` 的 source/target/aliases 做 hash。

**测试**：`StoryMemoryGlossaryRevisionTest`：
- 只改术语 → hash 变；
- 只加人物/风格/摘要 → hash 不变；
- 空术语 → `""`。

### E2. sidecar 记录翻译时实际使用的术语版本（P1）

**方案**：

1. `ChapterSidecar` 新增可选字段：

```kotlin
@SerialName("glossary_hash") val glossaryHash: String? = null,
```

2. `TranslationConfig` 新增 `glossaryHash: String = ""`；
   `AppSettings.toTranslationConfig` 设置
   `glossaryHash = StoryMemoryStore.glossaryRevision(memory)`。
3. 写 sidecar 的四处全部带上：`ChapterTranslator.sidecar`、
   `TranslationService.polishChapter`、`TranslationService.retranslateParagraph`。
4. `ReaderViewModel.syncSidecarRevision` 不再覆盖术语字段：

```kotlin
sidecar.copy(
    translationConfigHash = config.cacheKey(),
    storyRevision = revision,
)
```

`glossaryRevision` 与 `glossaryHash` 保留翻译时的值。

**兼容**：旧 sidecar 没有 `glossary_hash`，反序列化为 null；
`SidecarJson` 的 `ignoreUnknownKeys = false` 意味着旧版本 App 读新文件会失败，
但本项目只支持单向升级，自检注明。

### E3. 过期判定（P1）

新增纯函数 `feature/reader/TranslationFreshness.kt`：

```kotlin
internal fun glossaryOutdated(
    sidecarGlossaryHash: String?,
    sidecarRevision: String?,
    currentGlossaryHash: String,
    currentCombinedRevision: String,
): Boolean {
    if (!sidecarGlossaryHash.isNullOrBlank()) {
        return currentGlossaryHash.isNotBlank() &&
            sidecarGlossaryHash != currentGlossaryHash
    }
    // 旧数据：沿用综合 revision 比较
    return currentCombinedRevision.isNotBlank() &&
        sidecarRevision != currentCombinedRevision
}
```

`ReaderViewModel`：

- 新增 `private var currentGlossaryHash: String = ""`；
- `applyMemory` / `refreshStoryMemory` 设置
  `StoryMemoryStore.glossaryRevision(memory)`；
- `staleReasons` 的 `glossaryChanged` 改为调用上述函数。

**测试**：`TranslationFreshnessTest` 四个分支（新字段匹配/不匹配、
旧字段匹配/不匹配）。

### E4. 元数据缓存把「有标题」当完成（P2）

`MetadataTranslationService.translateBook`：

```kotlin
if (cached?.sourceHash == sourceHash && cached.metadata.titleZh.isNotBlank()) {
    return cached.metadata
}
```

**方案**：

```kotlin
val missingSynopsis = synopsis.isNotBlank() &&
    cached?.metadata?.synopsisZh.isNullOrBlank()
if (cached?.sourceHash == sourceHash &&
    cached.metadata.titleZh.isNotBlank() &&
    !missingSynopsis
) {
    return cached.metadata
}
```

源简介本来就是空的书不强制要求译文简介。

**测试**：`MetadataTranslationServiceTest` 新增：第一次返回只有标题、
第二次返回标题+简介；两次调用后 `calls == 2`，简介补上。

### E5. 版本与文档

- `versionCode = 58`，`versionName = "1.7.2"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。
- 指南与自检写入 `android/docs/upgrade/round-21/`。

## 2. 实施顺序

1. `glossaryRevision` + 测试。
2. sidecar 新字段与四处写入。
3. `glossaryOutdated` + `ReaderViewModel` 接线 + 测试。
4. `translateBook` 缓存条件 + 测试。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 283，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 58。

## 4. 风险

- 旧 sidecar 没有 `glossary_hash`，首次升级仍走旧逻辑，可能继续误报一次；
  重新翻译后自动转为新逻辑。
- `syncSidecarRevision` 不再覆盖术语字段，旧逻辑下若 `storyRevision` 未更新，
  旧数据仍按原行为比较，不会更糟。
- 新增 sidecar 字段对备份/恢复透明（JSON 可选字段）。
