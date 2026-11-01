---
name: lightnovel
description: 轻小说一条龙：按口味画像去上游源站挖冷门但对口的日文轻小说、按需增量翻译成简体中文（带术语表/人物/前情梗概的"故事记忆"）、并起一个书架网站「点开就读、读到哪翻到哪」，也支持导入本地 EPUB/TXT。当读者想找轻小说/要推荐/问更新、想翻译某部日文生肉、想导入手里的 EPUB/TXT、要看已翻译的书、要「开网站看小说」问书架地址、要把网站开给平板/局域网、或要维护自己的口味画像时使用。
whenToUse: 读者说「找/推荐轻小说」「最近有什么好看的」「推荐几本」「按标签找书」「这个作者还有别的书吗」；「帮我翻这本/这章」「接着往下翻」「从我看到的地方接着翻」「这名字翻得不对」；「开网站」「书架地址是什么」「服务还在跑吗」「平板也要能看」「手机热点」；或抱怨通用 AI 只推大热作品、某本太套路。注意：token 预算有限，**绝不要一次翻整本**，也绝不自动翻没看过的书。
---

# 轻小说：找书 → 翻译 → 书架网站

三件事：**找书**（`lnfinder/`）→ **按需翻译**（`lntrans/`）→ **书架网站**（`lntrans/lnserve.py`）。
日常最常用的是「开网站」，就是下一节，不用读别的文件。

## 怎么用（省 token：只读需要的那份）

本 skill 目录下的 `references/` 存其余文档，**按需只读一份**（用 `read`）：

| 你要做的事 | 读哪个 |
| --- | --- |
| 起服务、打开网站、确认服务在不在 | **本文件 §0（下面）** |
| 找书、推荐、调画像、负反馈 | `references/finder.md` |
| 翻译、术语表、翻译策略、成本 | `references/translate.md` |
| 校对、观察池、翻译经验自进化、多书隔离 | `references/translate.md` 的「校对与自进化」 |
| 网站实现、面板、前端、状态机 | `references/lnserve.md` |
| 踩坑清单、自检铁律、改动前自查 | `references/lessons.md` |
| 换机器 / 分享给别人 / 目录硬规矩 | `references/setup.md` |
| 在**手机**上接手（环境差异、硬边界） | `PHONE-HANDOFF.md`（两页） |
| 改代码前 | `references/lessons.md` + 对应模块那份 |

`references/` 与本文件同目录（skill 目录见系统提示里的 location）。

---

## 0. 开网站（最常用的一条）

```bash
cd <工具目录>/lntrans
python3 lnserve.py --port 8099          # 只在本机
python3 lnserve.py --port 8099 --lan    # 顺便开给局域网（手机热点 → 平板）
```

然后浏览器打开 **http://127.0.0.1:8099/**

要点（这几条都是踩过的）：

* **先看有没有部署配置**：如果部署方留了 env 文件或启动脚本（例如 `$HOME/.ln-phone.env`
  或 `~/ln-phone.sh`，见 `PHONE-HANDOFF.md` §8），**先用它**再起服务
  （`set -a; . <env文件>; set +a`，或直接跑那个脚本）。裸跑 `python3 lnserve.py`
  会读代码目录里的旧数据根、连默认云端端点 —— 主库在别处，本地模型也不会生效。
* 服务**不是常驻的**：它随会话/终端结束而死。要读之前先确认它在跑：

  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8099/   # 要看到 200
  ```

  不是 200 就重新起（用后台任务跑，别前台阻塞，否则会把会话卡死）。
* **绝不用 `pkill -f lnserve.py`** 停服务：那条命令自己的 cmdline 里也含
  `lnserve.py`，会把自己这条 shell 一起杀掉（踩过两次）。要停就用**精确 argv 匹配**：
  遍历 `/proc/<pid>/cmdline`，只杀 argv 里真的以 `lnserve.py` 结尾的那个进程。
* 首屏是三个页签（hash 路由 `#recs` / `#shelf` / `#lib`）：
  * **🎯 推荐** —— 按画像打分 + 命中理由 + 「＋ 加入书架」
  * **📚 书架** —— 收藏 / 在读 / 想读 / 看完 / 弃文 + 更新提示
  * **🗂 书库** —— 凡是爬过的书都留档，可搜、可标想看、可隐藏
* 另外两个入口：阅读页 `/read/<slug>`（点书就进）、详情页 `/book?id=<源站id>`。
* **本地书**：首页/设置页的「导入本地 EPUB / TXT」(`/import`) 上传文件即建书，
  自动进书架「想读」；命令行 `python3 lntrans.py import <文件>` 也可以（同样会上架）。
* **译名过时**：术语表改过之后，阅读页会给用到旧译名的章节一条提示，可一键重翻
  本章；命令行用 `python3 lntrans.py stale <slug>` 先看（只报告，不花 token）。
* `--lan` 会绑 `0.0.0.0`，页面底部会多一行「📱 平板/其他设备访问：…」。
  地址是 **现查**的（`/api/net`）：热点开关一次网卡和 IP 都会变，
  启动时算好写死就会过期。
* **`--lan` 使用表单登录**：启动日志给出地址和口令，但**网址不携带口令**。
  平板打开地址后输入一次；登录成功只保存随机会话 Cookie，不保存主口令。
  可用 `LNTRANS_TOKEN` 或 `LNTRANS_TOKEN_FILE` 固定口令；自定义域名用
  `LNTRANS_ALLOWED_HOSTS` 加入 Host 白名单。跨站写请求、伪造 Host、暴力登录
  和频繁启动翻译都会被拒绝或限速。**回环地址 `127.0.0.1` 免登录**。
  公共 Wi-Fi 下仍建议用 HTTPS/Tailscale，不要直接把服务暴露到公网。
* 服务起来之后**别停**：用户都在这个网页里读书、收藏、点反馈。
  改完代码要重启才会生效（Python 不热载）。

---

## 其余任务的一句话入口

* **找书 / 推荐** → `references/finder.md`（`<工具目录>/lnfinder/lnfind.py`）
* **翻译** → `references/translate.md`（`<工具目录>/lntrans/lntrans.py`）
* **导入本地 EPUB/TXT、术语过期重翻、章节名/候选术语** → `references/translate.md`
* **校对 / 沉淀经验** → `review <slug>`、`lessons <slug>`（报告按书隔离）
* **部署 / 分享 / 目录硬规矩** → `references/setup.md`
* **改代码前** → `references/lessons.md` + 对应模块那份
