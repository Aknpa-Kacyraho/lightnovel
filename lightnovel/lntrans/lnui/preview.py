"""Zero-data visual acceptance page for the next UI."""

from __future__ import annotations

from pathlib import Path

from .components import badge, button, card, empty, field, select
from .layout import shell
from .styles import css

_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "lnui-preview.js"


def _controls() -> str:
    return '''
<div class="ui-preview-bar">
  <div class="ui-preview-brand"><span class="ui-preview-kicker">UI NEXT</span>
    <b>视觉验收</b><span>不接数据 · 不进导航</span></div>
  <div class="ui-preview-controls">
    <span class="ui-preview-label">管理主题</span>
    <button class="ui-chip on" data-ui-theme="light" type="button">暖纸</button>
    <button class="ui-chip" data-ui-theme="dark" type="button">夜间</button>
    <span class="ui-preview-label">阅读主题</span>
    <button class="ui-chip on" data-reading-theme="light" type="button">浅色</button>
    <button class="ui-chip" data-reading-theme="dark" type="button">深色</button>
    <span class="ui-preview-label">字号</span>
    <button class="ui-chip" data-reading-size="16" type="button">小</button>
    <button class="ui-chip on" data-reading-size="18" type="button">中</button>
    <button class="ui-chip" data-reading-size="21" type="button">大</button>
    <span class="ui-preview-label">视口</span>
    <button class="ui-chip" data-viewport="390" type="button">390</button>
    <button class="ui-chip" data-viewport="768" type="button">768</button>
    <button class="ui-chip on" data-viewport="1200" type="button">1200</button>
  </div>
</div>'''


def _sample() -> str:
    cards = "".join([
        card(
            title="我虽被称为新锐百合漫画家，其实并不太懂百合是什么",
            subtitle="気鋭の百合漫画家と呼ばれている私だが、実は百合という…",
            synopsis="虽然我并不打算画百合的……檀本咲鸣@二代目圣女漫画化连载中！",
            meta="檀本咲鸣 · 浪漫 · 58 话",
            tags=["百合", "漫画化", "恋爱"],
            actions=(button("直接阅读", tone="primary", icon_name="play")
                     + button("加入书架", tone="secondary")),
            tone="featured",
        ),
        card(
            title="【完结】从强制劳动设施逃走后，在魔法少女所在的世界TS了",
            subtitle="【完結】強制労働施設から逃げた、魔法少女のいる世界…",
            synopsis="不习惯应付女人的男人，有时会惊人地轻易结自己的人生。",
            meta="ふかしぎ · 学园 · 54 话",
            tags=["TS", "魔法少女", "完结"],
            actions=(button("直接阅读", tone="primary", icon_name="play")
                     + button("加入书架", tone="secondary")),
        ),
        card(
            title="关于对能看见卡牌精灵的玩家使用『夺取控制权』战法后场面实在太惨不忍睹这件事",
            subtitle="カードの精霊が見えるプレイヤー相手に、コントロール奪…",
            synopsis="不对！刚才那是我的卡牌自己擅自动的！废工厂厂长·动作·10话",
            meta="废工厂厂长 · 动作 · 10 话",
            tags=["卡牌", "喜剧", "异世界"],
            actions=(button("直接阅读", tone="primary", icon_name="play")
                     + button("加入书架", tone="secondary")),
        ),
    ])
    form = (
        '<div class="ui-form-grid">'
        + field("显示名称", "display_name", value="灯下读者",
                help_text="只在本机显示。")
        + field("每日 token 预算", "budget", kind="number", value="300000",
                help_text="0 表示不限；本地模型不计数。")
        + select("默认阅读主题", "reading_theme",
                 [("light", "浅色"), ("dark", "深色")], selected="light")
        + '</div>'
    )
    return f'''
<div class="ui-main-inner">
  <div class="ui-stack">
    <section class="ui-section">
      <div class="ui-section-head">
        <div><span class="ui-kicker">DISCOVER</span><h2>今天适合读什么</h2>
          <p>从标签、相似作品和你还没读过的书里挑。</p></div>
        <div class="ui-section-actions">{button("换一批", tone="ghost")}</div>
      </div>
      <div class="ui-grid ui-grid-3">{cards}</div>
    </section>

    <section class="ui-section ui-split">
      <div>
        <div class="ui-section-head"><div><span class="ui-kicker">FORM</span>
          <h2>表单与状态</h2><p>设置、导入和筛选共用同一套控件。</p></div></div>
        <div class="ui-panel">{form}
          <div class="ui-inline-actions">
            {button("保存设置", tone="primary")}{button("取消", tone="ghost")}
            {badge("已保存", tone="ok")}{badge("需要重试", tone="warn")}
            {badge("本地导入", tone="local")}
          </div>
        </div>
      </div>
      <div>
        <div class="ui-section-head"><div><span class="ui-kicker">EMPTY</span>
          <h2>空状态</h2><p>没有数据时也要告诉用户下一步。</p></div></div>
        <div class="ui-panel">{empty("书库还是空的", "从发现页挑一本，或导入你自己的 EPUB/TXT。", button("去发现", tone="primary"))}</div>
      </div>
    </section>

    <section class="ui-section">
      <div class="ui-section-head"><div><span class="ui-kicker">READING</span>
        <h2>阅读器正文</h2><p>管理页和阅读器各自持有主题作用域。</p></div></div>
      <div class="ui-reading">
        <div class="ui-reading-meta"><span>第 12 章 · 雨夜</span><span>68%</span></div>
        <p>雨声落在窗沿上，像有人在很轻地敲门。她把书翻到下一页，却没有看进去。</p>
        <p>「你还在等吗？」<br>「没有。」她回答得太快了。</p>
      </div>
    </section>
  </div>
</div>'''


def preview_js() -> str:
    text = _JS_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"preview script is empty: {_JS_PATH}")
    return text


def render_preview() -> str:
    body = shell(
        active="发现",
        eyebrow="视觉基线 · 零数据",
        title="灯下",
        subtitle="把发现、收藏和阅读收进同一套壳里。",
        actions=button("设置", tone="ghost", icon_name="settings"),
        content=_sample(),
    )
    return f'''<!doctype html>
<html lang="zh-CN" data-ui="next">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>灯下 · UI 预览</title>
<link rel="icon" href="data:,">
<style>{css()}</style>
</head>
<body class="ui-preview-body">
{_controls()}
<div class="ui-preview-stage" data-preview-stage data-theme="light"
     data-reading-theme="light" data-reading-size="18" data-viewport="1200">
{body}
</div>
<script>{preview_js()}</script>
</body></html>'''
