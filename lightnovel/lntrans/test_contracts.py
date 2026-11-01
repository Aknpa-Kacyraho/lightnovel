#!/usr/bin/env python3
"""Parse-contract tests frozen for v5 job logs and chapter sidecars."""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lncontracts as c

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


JOB = {
    "schema_version": 1,
    "job_id": "job-1",
    "idempotency_key": "book-a:12:hash",
    "slug": "book-a",
    "status": "interrupted",
    "target": {"from_chapter": 12, "to_chapter": 14},
    "model_provider": "local",
    "model_role": "translate",
    "model_id": "model-a",
    "usage": {"input": 100, "output": 50},
    "cost": {"amount": 0.01, "currency": "CNY", "estimated": False},
    "created_at": "2026-10-21T12:00:00+08:00",
    "updated_at": "2026-10-21T12:01:00+08:00",
    "error": None,
}
check("合法任务记录通过", c.validate_job_record(dict(JOB)) == JOB)

bad = dict(JOB, status="mystery")
try:
    c.validate_job_record(bad)
    rejected = False
except c.ContractError:
    rejected = True
check("未知任务状态被拒绝", rejected)

high = dict(JOB, schema_version=2)
try:
    c.validate_job_record(high)
    rejected = False
except c.ContractError:
    rejected = True
check("未来任务 schema 被拒绝", rejected)

SOURCE = "a" * 64
kw = dict(
    source_sha256=SOURCE,
    model_provider="openai-compatible",
    model_id="translate-model",
    prompt_version="ln-prompt-5",
    glossary_revision=3,
    characters_revision=2,
    style_revision=1,
)
h1 = c.translation_config_hash(**kw)
h2 = c.translation_config_hash(**dict(kw, model_id="other-model"))
check("配置哈希稳定且区分实际模型",
      len(h1) == 64 and h1 != h2)

META = {
    "schema_version": 1,
    "status": "complete",
    "source_sha256": SOURCE,
    "content_sha256": "c" * 64,
    "translation_config_hash": h1,
    "model_provider": "openai-compatible",
    "model_role": "translate",
    "model_id": "translate-model",
    "prompt_version": "ln-prompt-5",
    "translated_at": "2026-10-21T12:03:00+08:00",
    "tokens": {"input": 100, "output": 200},
    "cost": {"amount": 0.02, "currency": "CNY", "estimated": True},
    "incomplete_paragraphs": [],
}
check("合法章节旁车通过", c.validate_chapter_meta(dict(META)) == META)
check("内容可用：文件存在且原文未变",
      c.content_available(META, translation_exists=True,
                          current_source_sha256=SOURCE,
                          current_content_sha256="c" * 64))
check("原文变了则内容不可用",
      not c.content_available(META, translation_exists=True,
                              current_source_sha256="b" * 64,
                              current_content_sha256="c" * 64))
check("正文与旁车错配则内容不可用",
      not c.content_available(META, translation_exists=True,
                              current_source_sha256=SOURCE,
                              current_content_sha256="d" * 64))
check("配置改变不影响旧译文可读",
      not c.current_config_satisfied(META, h2)
      and c.content_available(META, translation_exists=True,
                              current_source_sha256=SOURCE,
                              current_content_sha256="c" * 64))

bad_meta = dict(META, model_role="review")
try:
    c.validate_chapter_meta(bad_meta)
    rejected = False
except c.ContractError:
    rejected = True
check("章节旁车拒绝非翻译模型角色", rejected)

partial = dict(META, status="partial", incomplete_paragraphs=[3, 7])
check("partial 章节带缺失段仍可读",
      c.validate_chapter_meta(partial)
      and c.content_available(partial, translation_exists=True,
                              current_source_sha256=SOURCE,
                              current_content_sha256="c" * 64))
for label, value in (
    ("complete 不允许缺失段",
     dict(META, status="complete", incomplete_paragraphs=[1])),
    ("partial 必须列出缺失段",
     dict(META, status="partial", incomplete_paragraphs=[])),
    ("complete 不允许 incomplete_reason",
     dict(META, incomplete_reason="provider_incomplete")),
):
    try:
        c.validate_chapter_meta(value)
        rejected = False
    except c.ContractError:
        rejected = True
    check(label, rejected)

for name in ("job-v1.schema.json", "chapter-meta-v1.schema.json"):
    path = os.path.join(HERE, "contracts", name)
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    check(f"{name} 可解析且有版本字段",
          schema.get("$schema") and "schema_version" in schema.get("properties", {}))

print()
if fails:
    print(f"失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("任务与章节旁车契约解析全部通过")

