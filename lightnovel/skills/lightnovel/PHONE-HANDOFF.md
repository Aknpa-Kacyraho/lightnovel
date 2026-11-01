# 手机 DSH 交接（前辈留言）

> 先读同目录的 `SKILL.md`（入口 + 开网站），再按它的路由表只读 `references/` 里相关的那份；本页只补三件事：
> **手机环境差异、绝对不能碰的边界、最近一轮踩过的坑。**
> 目标：少走弯路，别把用户的数据和钱弄丢。

## 1. 三条硬边界（先记住）

1. **绝不写用户真实数据**：`lnfinder/taste_profile.json`、`history.jsonl`、
   `candidates.json`、`reports/`、`lntrans/novels/`、`lntrans/data/`、
   `lntrans/*-中文.md`、任何凭据文件。
   跑测试/维护脚本前，先把 `LNTRANS_DATA_ROOT`、`LNTRANS_LNFINDER`
   指向临时目录；跑完确认真实目录指纹没变。
2. **绝不打印/提交 key、token、家目录绝对路径**。key 只从
   `DEEPSEEK_API_KEY` 或 `LNTRANS_CRED` 指向的文件读。
3. **停服务绝不用 `pkill -f lnserve.py`**：那条命令自己的 cmdline 也含
   `lnserve.py`，会连自己一起杀。按 `/proc/<pid>/cmdline` 精确匹配 argv。

## 2. 手机（Android / Termux）环境差异

- `python3`，**纯标准库，不需要 pip 装任何东西**。
- `fcntl` 是真的，不需要电脑上那个 Windows 桩；`chcp 65001` 也不需要。
- `node` 可能没装：它只用于前端语法检查。**缺 node 时自检会判失败**
  （这是故意的，不允许静默跳过）。要跑全套就先 `pkg install nodejs`，
  否则接受 `test_js_static` 失败，别去把断言改松。
- 起服务（服务不常驻，读完/改完要重启）：

  ```bash
  cd <工具目录>/lntrans
  python3 lnserve.py --port 8099          # 只本机
  python3 lnserve.py --port 8099 --lan    # 开给平板（有随机口令，见启动日志）
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8099/   # 要 200
  ```

- 自检（唯一入口，**不联网、不花钱**）：

  ```bash
  cd <工具目录>/lntrans && python3 run_selftests.py       # 35 个，全绿才算过
  cd <工具目录>/lntrans && python3 run_selftests.py -v    # 看每条断言，防假绿
  cd <工具目录>/lntrans && python3 run_selftests.py -k test_ui,test_state
  cd <工具目录>/lnfinder && python3 selftest.py
  ```

## 3. 每次改代码的固定流程

1. 先读对应函数/文档段：`SKILL.md` 已很短，其余按路由表只读 `references/` 里那份；`lnserve.py` **别整份加载**。
2. 改之前问三句：
   - 这个语义是不是已经有**一份**实现？（有就复用，别再写第二份）
   - 这个数字是「总数」还是「这一屏画出来的数」？（不一致就都写出来）
   - 这个状态字段谁置位、谁清除、谁读？（缺清除路径迟早亮假徽标）
3. 改完：全套自检绿 → `lnfinder` 自检绿 → 报「改了哪些文件 + 跑过哪些测试」。
4. **不要为了变绿放宽断言**；空数据/缺环境导致的 skip 一律算失败。
5. 只有用户要求时才打包；打包前确认**所有编辑都已落盘**。

## 4. 最近一轮修过的坑（别又改回去）

| 问题 | 现在的护栏 | 回归 |
| --- | --- | --- |
| 「更新了」徽标假阳性 / 永不清除 | `_clear_update_flags()`；复查无新章时清；弃文/移出也清；首页/卡片/`watch_list()` 统一用 `_item_watches()` | `selftest3`、`test_state` K 段、`selftest4` A2 |
| 译不出标记成功后不清 | `translate_one` 成功分支 `pop` 对应 failed | `test_detail` A2 |
| 源站宕机时每次打开都重试 | 失败也写 `check_attempt_at`，去重看它 | `selftest3` C 段 |
| `?page=abc` / 非数字参数打成 500 | 一律走 `_as_int(v, default, lo, hi)` | `test_ui` F 段 |
| 列表截断后数字骗人 | 总数与渲染数同源；截断写「显示前 N」（标签 60 / 分卷 400） | `test_detail` A3/A4 |
| 卡片 HTML 转义混用 | 文本 `lr.esc`，属性 `attrescape`；含 `library_pane`、阅读页 `data-slug` | `test_state` 第 16 段 |
| 自检假绿 | 环境缺失文案进 `SKIP_AS_FAIL`；核心测试缺文件/服务未起直接判失败；空书库 `exit 1`；node 缺失判失败 | runner 自身 |
| `--lan` 日志块缓冲藏口令 | `main()` 开头 `reconfigure(line_buffering=True)` | 重定向日志 2 秒内可见 |
| 维护脚本空环境崩溃 | `repair_chrome.py` 先判断目录存在，友好退出 0 | 空数据根干跑 |
| zip 只更新一半 | 所有编辑落盘后再打包；逐条字节比对 `MISMATCH=0` | 三步核验 |

## 5. 代码地图（别整份读大文件）

- `lntrans/lnserve.py`：HTTP 服务、worker、全部页面渲染。按函数名定位。
- `lntrans/lntrans.py`：翻译核心（分段、校验、重试）。
- `lntrans/lnrecs.py`：推荐缓存 + 书库留档。
- `lntrans/lnrender.py`：章节 HTML。
- `lntrans/static/*.js`：前端脚本；改完要 `node --check`。
- `lntrans/test_*.py`、`run_selftests.py`：回归。
- **`AGENTS.md`（工具目录）**：更细的硬规则与踩坑清单，改代码前先看。

## 6. 打包给手机（只有被要求时）

- 备份旧包到 `$TMPDIR`（Termux）或 `/tmp`。
- 从 `<工具目录>` 打包，**排除**：`lntrans/novels/`、`lntrans/data/`、
  `__pycache__/`、`lnfinder/taste_profile.json`、`candidates.json`、
  `history.jsonl`、`reports/`、`recommend-latest.md`、`*-中文.md`、凭据类。
- 核验三步：① 排除项 0；② 必备项 0 缺失；③ 逐条字节比对
  `MISMATCH=0`，关键文件行数/字节与源码一致。
- 可选但推荐：解压到空目录起服务冒烟，`/` 必须 200、未知书页 404。

## 7. 遇到不确定

- 先查 `SKILL.md` 的路由表 → `references/` 对应文件 + 工具目录的 `AGENTS.md`。
- 手机上没有第二个窗口互评，**拿不准就问用户**，别猜口味、别自动翻
  没看过的书、别一次翻整本（token 很贵）。
- 交付时说清楚：已验证什么、没验证什么、有什么限制。

## 8. 部署与数据根（本轮经验）

- **主库可以在代码目录之外**：常见形态是 `LNTRANS_DATA_ROOT=$HOME/lightnovel-data`，
  配置集中在一个 `600` 权限的 env 文件里，起服务前 `set -a; . <env文件>; set +a`。
  启动日志会打印「作品目录」，先核对它指向主库，而不是代码目录里的旧留档。
- **同一份数据只许一个进程写**：换根前先停服务，再用 `lnbackup.py` 或 `cp -a` 复制；
  旧根原样保留当回滚点，**不要** `mv` 掉它，也不要两边同时起服务。
- **按角色路由**（`lnmodels`）：翻译/辅助可走本地引擎，校对单独走
  `LNTRANS_LLM_BASE_URL_REVIEW`；`LNTRANS_LLM_FALLBACK=1` 时主端点连接失败
  （连接/超时/401/404/5xx）会在 120 秒内切云端 `deepseek-flash`，日志会写
  `⚠ translate 主端点失败（…），120 秒内改用 deepseek/deepseek-flash`。
  400/422 不切（那是请求本身的问题，换端点也没用）。
- **句子级模型（Sakura 等）给它单独一条路，别塞进批量编号**（2026-10-22 实测）：
  7B 给 20 行编号漏 7 行、60 行漏 28 行 —— 因为它按句子输出，会把几行并成一句。
  现在 `LNTRANS_TRANSLATE_MODE=sakura`：用它自己的「将下面的日文文本翻译成中文：…」
  模板，并且**整章一块**送（块大小按模型分档：本地 `LNTRANS_CHAPTER_CHARS`
  默认 2160（实测上限 ~2400 的 90%）；DeepSeek `LNTRANS_DEEPSEEK_CHAPTER_CHARS` 6000，
  块间续上下文）。实测一章 1~3 次请求、约 1 分钟、**0 元**，语义比一段一段连贯；
  失败块留原文、本章仍写出并标「未译全」。批量模式留给 DeepSeek 这样的大模型。
  别放宽「编号必须齐全」的断言，也别把整章拆回逐段。
- **兜底是 2 秒探测、不是等超时**：PC 关机时 `lnmodels.probe` 先摸端口，
  不通就立刻切 DeepSeek（日志 `主端点不可达`）；PC 回来后 120 秒熔断期满自动再试本地。
- **DeepSeek 整章翻**：它现在也用通用整章格式（一章一次请求），思考 token 算在
  max_tokens 里，给小了会截断/空回复，云端单次默认 32000。
- **弃文 / 看完 = 停止花钱**：只写书状态不够，调度器还记着"在读"会继续翻；
  现在同时暂停调度并取消当前任务，恢复要显式点「继续翻译」。
