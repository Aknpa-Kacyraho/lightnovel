# 首次部署 / 分享 / 目录硬规矩

> 换机器、分享给别人、改代码前看这里；日常开网站只需 SKILL.md 的 §0。
> 对应原文档的 §0.1–§0.3。

---

## 0.1 首次部署（换一台机器 / 分享给别人）

依赖极简：

* **Python 3.10+（本机 3.12 上验证）**，只用标准库 —— **不需要 pip 装任何东西**
* 可选 `node`：只用来把页面里的内联 JS 编译一遍（前端唯一能自动化的验证手段）
* 需要联网的地方只有两处：找书打上游源站（Kakuyomu）、翻译打 LLM API

步骤：

1. **拷代码 + skill 文件**（只拷代码，绝不拷数据）：只需要 `lnfinder/` 与 `lntrans/`
   两个目录里的代码（`.py` / `.md`，以及 `lntrans/static/` 下的前端 `.js`），外加本
   skill 文件。直接跑下面这段就能得到干净的一份（按需改路径）：

   ```bash
   SRC=<工具目录>                 # 例如 /path/to/lightnovel
   DEST=/tmp/lightnovel-share
   rm -rf "$DEST"; mkdir -p "$DEST"
   cp -r "$SRC/lnfinder" "$SRC/lntrans" "$DEST/"
   cd "$DEST"
   # 个人数据：画像 / 候选池 / 报告 / 译文 / 阅读数据
   rm -rf lnfinder/reports lnfinder/candidates.json lnfinder/history.jsonl \
          lnfinder/taste_profile.json lnfinder/recommend-latest.md \
          lntrans/novels lntrans/data
   # 导出的译文文件（文件名常是「<日文书名>-中文.md」，一律删掉）
   find lntrans -maxdepth 1 -name '*.md' ! -name 'STATE-MACHINE.md' \
        ! -name 'PRIOR-ART.md' -delete
   # skill 文件本身也要给出去（对方放进自己 agent 的 skills 目录）。
   # 代码可以放在任意目录 —— skill 里统一用 <工具目录> 指代。
   mkdir -p "$DEST/skills"
   # skill 目录本身（SKILL.md + references/）整个拷过去；路径按你的 agent 布局改
   # （手机侧是 .dsh/skills/lightnovel，本仓库 PC 副本是 skills/lightnovel）
   cp -r "$SRC/skills/lightnovel" "$DEST/skills/"
   # 最后一步：清缓存 + 自查（**跑过自检之后 .pyc 会重新生成，给出去前再删一次**）
   find . -name __pycache__ -type d -exec rm -rf {} +
   grep -rniE "sk-[A-Za-z0-9]{16,}|api[_-]?key *[:=] *[^ ]|authorization: *bearer" . | head
   grep -rnE "/root/|/home/[a-z]" . | head
   du -sh "$DEST"
   ```
2. **配 key**（翻译/校对需要；找书/推荐不需要任何 key）：

   ```bash
   # 纯云端
   export LNTRANS_LLM_API_KEY=sk-...
   export LNTRANS_LLM_BASE_URL="https://api.deepseek.com/chat/completions"

   # 本地翻译 + DeepSeek 校对 + 本地挂了自动切云端
   export LNTRANS_LLM_BASE_URL="http://127.0.0.1:11434/v1/chat/completions"
   export LNTRANS_LLM_API_KEY=<本地引擎 key，可空>
   export LNTRANS_MODEL_TRANSLATE=<本地模型 id>
   export LNTRANS_MODEL_AUXILIARY=<本地模型 id>
   export LNTRANS_LLM_BASE_URL_REVIEW="https://api.deepseek.com/chat/completions"
   export LNTRANS_MODEL_REVIEW=deepseek-flash
   export LNTRANS_LLM_FALLBACK=1
   export LNTRANS_LLM_FALLBACK_BASE_URL="https://api.deepseek.com/chat/completions"
   export LNTRANS_LLM_FALLBACK_MODEL=deepseek-flash
   # 旧 DEEPSEEK_API_KEY / LNTRANS_LLM_BASE 仍兼容；本地回环端点可完全不配 key。
   # 也可写凭据文件：export LNTRANS_CRED=/path/to/creds.yaml
   ```

   key 只从环境变量或凭据文件读，**代码里不存**，任何日志/输出也不打印。
   完整变量见包内 `.env.example` 与 `docs/MODEL-CONFIG.md`。
3. **建自己的画像**，否则推荐出来的是别人的口味：

   * 源码里内置的 `DEFAULT_PROFILE.tag_weights`（口味权重）与
     `DEFAULT_SCAN_QUERIES`（搜索词）**是原作者的口味**，分享前换成你自己的或清空；
   * 第一次用：让 agent 问你的偏好（喜欢什么类型/讨厌什么套路），
     生成 `lnfinder/taste_profile.json`，再跑一轮 `scan` 看效果。
     细节见 `references/finder.md` 的「持续优化画像」。
4. **跑一遍自检**确认环境没坏（**自检不联网、不花钱**，自带桩 LLM）：

   ```bash
   cd <工具目录>/lntrans && python3 run_selftests.py    # 35 个，全绿才算过
   cd <工具目录>/lntrans && python3 run_selftests.py -v # 同上，另打印每条断言（确认不是假绿）
   cd <工具目录>/lnfinder && python3 selftest.py
   ```

   第 4 步很重要：它同时会告诉你"真实数据有没有被测试污染"。
5. 起服务 → §0。

---

## 0.2 个人信息清单（分享前必须排掉）

这套工具**故意**把"个人数据"和"代码"分开放。分享/迁移时：

| 绝对不要外传 | 里面是什么 |
| --- | --- |
| `lnfinder/taste_profile.json` | **你的口味画像**（喜欢/讨厌哪些标签、权重） |
| `lnfinder/history.jsonl` | 你的反馈历史（哪本对味/不对味） |
| `lnfinder/candidates.json`、`lnfinder/reports/` | 你扫过的候选池与报告 |
| `lntrans/novels/` | **你翻译过的书**（原文 + 译文 + 术语表 + 进度） |
| `lntrans/data/` | 推荐缓存、书库留档、详情缓存、books 状态、反馈 |
| 凭据文件（`CRED`，见 `lntrans.py`；可用 `LNTRANS_CRED` 指到别处）或任何 key 文件 | **API key** |
| `lntrans-backup-*.zip`（`lnbackup.py` 产物） | **上面所有东西的打包版**，体积小、最容易手滑一起发出去 |
| 会话记录、`/tmp` 里的测试残留 | 里面会有路径、书名、token 统计 |

自检的 `run_selftests.py` 会显式比对这些真实资产的指纹（跑前跑后必须一致）——
如果你改过测试，先确认它还在做这件事。

**分享前自查一遍**（在准备打包的目录里跑）：

```bash
grep -rniE "sk-[A-Za-z0-9]{16,}|api[_-]?key *[:=]|authorization: *bearer" . | head
grep -rn "/root/\|/home/[a-z]" . | head          # 别带出自己的家目录路径
```

---

## 0.3 目录与硬规矩

| 位置 | 是什么 | 能分享吗 |
| --- | --- | --- |
| `lnfinder/lnfind.py` | 画像、打分、负反馈学习 | ✅ 代码 |
| `lnfinder/lnlib.py` | 上游抓取（Kakuyomu 为主，小说家 API 作备） | ✅ 代码 |
| `lnfinder/selftest*.py` | lnfinder 自检 | ✅ 代码 |
| `lntrans/lnserve.py` | 书架 Web 服务（HTTP + 翻译 worker + 全部页面） | ✅ 代码 |
| `lntrans/lntrans.py` | 翻译核心（LLM 调用、分段校验、二分降级） | ✅ 代码 |
| `lntrans/lnrecs.py` | 推荐缓存 + 书库留档 | ✅ 代码 |
| `lntrans/lnrender.py` | 章节/整本 HTML 渲染 | ✅ 代码 |
| `lntrans/run_selftests.py` | **一键自检（唯一入口）** | ✅ 代码 |
| `lntrans/test_*.py`、`test_click_dom.js`、`selftest*.py` | 各模块回归（含「真点按钮」的前端仿真器 —— 别忘了带走那个 `.js`；`test_reader.py` 管章节划分/自动补章） | ✅ 代码 |
| `lntrans/repair_chrome.py` | 维护脚本：清掉历史章节里的网站页脚残留（见下文，会写数据，**分享包里可以带**） | ✅ 代码 |
| `lntrans/*.md` | 设计文档（状态机、前辈取舍、踩坑） | ✅ 文档 |
| `lnfinder/*.json`、`lnfinder/reports/` | 画像/候选池/报告 | ❌ **个人数据** |
| `lntrans/novels/`、`lntrans/data/` | 译文与阅读数据 | ❌ **个人数据** |

### 硬规矩：任何碰目录的模块都必须读环境变量，不许写死路径

踩过两次，而且都是"隔离测试把假数据写进真实目录"这种**看起来没事**的坑：

| 变量 | 含义 |
| --- | --- |
| `LNTRANS_DATA_ROOT` | 数据根（`novels/` + `data/`） |
| `LNTRANS_LNFINDER` | 画像/候选池等**数据**目录（注意：`lnfind.py` 代码始终在真实 `lnfinder/`） |
| `LNTRANS_HOME` | v5 单一数据根；设置后必须先用 `lnmigrate.py init/migrate` 初始化 |
| `LNTRANS_LLM_BASE` | LLM 端点；自检指向本地桩 LLM（**自检因此不花钱**） |
| `LNTRANS_LLM_BASE_URL` | 新版 LLM 端点变量；优先于旧名 |
| `LNTRANS_LLM_API_KEY` | 新版通用密钥；本地回环端点可不设 |
| `LNTRANS_MODEL_TRANSLATE` / `_AUXILIARY` / `_REVIEW` | 分别指定翻译、辅助、校对模型 |
| `LNTRANS_DAILY_BUDGET_CNY` / `LNTRANS_JOB_BUDGET_CNY` | 日预算 / 单任务预算，0 表示不限 |
| `LNTRANS_TOKEN` / `LNTRANS_TOKEN_FILE` | `--lan` 表单登录口令；文件建议放在数据根外。都不设则每次启动随机生成。回环地址免登录 |
| `LNTRANS_ALLOWED_HOSTS` | 额外允许的 Host 域名，逗号分隔；给 Tailscale / 反向代理域名用 |
| `LNTRANS_CRED` | 凭据文件路径（不设就用代码里 `CRED` 的默认值） |
| `LNTRANS_TEST_SERVER` | 标记"这是隔离测试服务"，测试据此决定能否做会写数据的检查 |

新加任何会写文件的模块，都要先读这几个变量，否则自检就会污染真实数据。
`run_selftests.py` 会给每个测试**单独一个数据根**，并且跑前跑后比对真实资产指纹 ——
看到"指纹不变"才算真的隔离住了。

v5 代际目录、迁移、回滚和跨进程锁见 `docs/V5-DATA-SAFETY.md`。应用代码可以
只读挂载；运行时只能写 `LNTRANS_HOME` 指向的那个数据卷。不要一边运行
`lnserve.py` 一边对同一数据根执行迁移或启动第二个实例。

变更型 `lntrans.py` 命令、`lnbackup.py export`、`restore --write` 会获取同一
数据根锁，因此服务运行时会被拒绝。`status`、`list`、`lessons`、`residue`、
`verify`、`info` 及干跑命令仍可只读运行。维护脚本和画像写入尚未全部接入
该锁，执行前先停服务；服务内备份也不能声称是翻译进行中的一致性快照。

### 通用工作方式

* **每次改动都做三方自检**（用户明确要求，别偷懒）：
  * **用户角度** —— 他真的会用到吗？操作路径是不是更长了？
  * **工程师角度** —— 真的验证过吗？隔离了吗？断言会不会假绿？
  * **设计师角度** —— 看得见吗？位置对吗？会不会被埋没（比如塞在 400 话目录后面）？
* **自主执行**：能自己决定的就做完再报告，别每一步都问。
* 报 bug 按**根因**修，不只修表面；修完顺手记进本文件（踩坑清单），别让它复发。
* **不许假绿**：断言要么真验证，要么显式失败。拿到空数据就 `skip` 掉的断言 = 没测。
* **调试脚本不许调真实 LLM**：又慢又真的花钱。自检自带桩 LLM；要端到端测就用它。
* 数值/文案**不能骗人**：显示的数量必须等于实际渲染的条数；耗时按实测写，不写"约 1 分钟"。
* 界面**中文优先**：中文大标题 + 日文小字副标题。
