# Lightnovel Reader Context

这个 context 描述“找书、入库、上架、翻译、阅读”这套轻小说工具里的领域语言。界面、迁移脚本和存储都应以这里的词为准。

## 书目

**Candidate**：
从源站抓来、尚未进入用户 catalog 的发现候选；可以整体丢弃和重建。
_Avoid_：书库、收藏

**Item**：
已经因为用户动作（收藏、想读、不喜欢、导入、加入书架）进入 catalog 的作品；候选升级为 item 后拥有用户状态。
_Avoid_：候选、书库条目

**Catalog**：
items、candidates、aliases 的唯一书目真相；候选区可重建，items 是真实资产。
_Avoid_：书库缓存、推荐缓存

**Source**：
作品来源的可扩展枚举，例如 `kakuyomu`、`syosetu`、`local`。
_Avoid_：站点、导入类型

## 书架

**Shelf**：
用户准备阅读的作品集合，状态为 `want`、`reading`、`finished`、`dropped`；`want` 允许尚未导入。
_Avoid_：书库、收藏

**Favorite**：
口味信号，不等于上架；收藏不会自动把作品放进 shelf。
_Avoid_：加入书架、想读

**Want**：
尚未开始阅读的上架意图；可以有占位卡，点开时才触发导入。
_Avoid_：收藏、未开始

**Hidden**：
用户明确“不喜欢/不再推荐”的作品状态；保留记录，但不参与新标签和推荐。
_Avoid_：删除、移出书架

**Imported**：
导入三态：`not_imported`、`importing`、`imported`；只有 `imported` 才可阅读。
_Avoid_：已在书架、已下载

**Import Checkpoint**：
导入过程中保留的完成摘要（格式版本、来源、内容哈希、章数、时间），供重试跳过已完成步骤。
_Avoid_：任务记录、下载缓存

**Import Interrupted**：
没有活跃导入任务、但 checkpoint 尚未完成的状态；catalog 仍是 `not_imported`，界面显示“继续导入”，不新增第四态。
_Avoid_：暂停导入、导入失败

## 身份与链接

**Id**：
内部主键，永久不变，也等于作品存储目录名；源站作品带命名空间前缀，本地作品使用稳定 UUID。
_Avoid_：slug、目录名（作为外部身份时）

**Slug**：
外部 URL 标识；内容变化时可以改变，但旧值必须进入 alias。
_Avoid_：id、标题

**Alias**：
旧 slug 到最终 slug 的扁平映射；alias key 永不复用，写入时递归解析到最终目标。
_Avoid_：重定向链、目录别名

**SourceFirstSeen**：
作品在源站候选池首次出现的时间，不可变。
_Avoid_：added_at、入库时间

**AddedAt**：
作品进入用户 catalog 的时间；新标签的 14 天判定只看它。
_Avoid_：first_seen、抓取时间

## 迁移

**Merge**：
把同一作品的两条记录合并为一条；本地记录为主，源站补全元数据，旧记录保留 `merged_into`。
_Avoid_：覆盖、删除旧记录

**Volume Key**：
从标题解析出的卷标识（如 `3`、`上`、`前編`）；属于身份的一部分，解析失败就不合并。
_Avoid_：卷号、标题后缀

**Approximate Mapping**：
旧进度映射中非完整命中的结果；必须带标记并写入迁移报告。
_Avoid_：模糊匹配、自动修正
