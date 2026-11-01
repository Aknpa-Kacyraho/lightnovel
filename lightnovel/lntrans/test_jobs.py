#!/usr/bin/env python3
"""Phase-2 fault tests: sidecars, durable jobs and read-only recovery."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="lnjobs-test-")
ROOT = os.path.join(TMP, "root")
PROFILE = os.path.join(TMP, "profile")
os.makedirs(os.path.join(ROOT, "novels"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
os.makedirs(PROFILE, exist_ok=True)
os.environ["LNTRANS_DATA_ROOT"] = ROOT
os.environ["LNTRANS_LNFINDER"] = PROFILE
os.environ.pop("LNTRANS_HOME", None)
sys.path.insert(0, HERE)

import lndata  # noqa: E402
import lncontracts  # noqa: E402
import lnjobs  # noqa: E402

fails: list[str] = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def put(rel: str, text: str) -> str:
    path = os.path.join(ROOT, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    old = sys.argv
    sys.argv = [name]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = old
    sys.modules[name] = mod
    return mod


def make_job(store, slug="book-a", source="a"):
    target = {"from_chapter": 1, "to_chapter": 2}
    config = "c" * 64
    key = lnjobs.idempotency_key(
        slug=slug, target=target,
        sources=[{"chapter": 1, "source_sha256": "d" * 64},
                 {"chapter": 2, "source_sha256": "e" * 64}],
        translation_config_hash=config)
    return store.create(
        slug=slug, target=target,
        model_provider="local", model_role="translate",
        model_id="stub-model", translation_config_hash=config,
        idempotency_key=key,
        requested={"count": 2, "reason": "test", "after": 1,
                   "fill": False, "ceiling": 2},
        source_entries=[{"chapter": 1, "source_sha256": source * 64}],
    )


print("=" * 66)
print("1. 章节旁车：兼容旧数据，校验新正文")
print("=" * 66)
put("novels/book-a/meta.json", json.dumps({
    "work_id": "book-a", "slug": "book-a", "source_id": "a",
    "title": "测试书", "episodes": [
        {"id": "e1", "title": "第一话"},
        {"id": "e2", "title": "第二话"},
    ],
    "glossary": {"猫": "猫"}, "characters": {}, "style": {},
}, ensure_ascii=False))
raw1 = put("novels/book-a/raw/0000.txt", "猫がいる。\n\n雨が降る。\n")
zh1 = put("novels/book-a/chapters/0000.txt", "有猫。\n\n下雨了。\n")

lt = load_module("lntrans", "lntrans.py")
check("旧版无旁车的章节仍可读", lt.has_translation("book-a", 0))

meta = lt.load_meta("book-a")
args = argparse.Namespace(model="stub-model", temperature=0.0)
text = open(zh1, encoding="utf-8").read()
raw_sha = lt._sha256_file(raw1)
record = lt.chapter_meta_record(
    "book-a", 0, meta, args, text=text, raw_sha=raw_sha,
    tokens_in=120, tokens_out=80, incomplete_paragraphs=[])
lt.save_json(lt.chapter_meta_path("book-a", 0), record)
check("完整旁车让正文可用", lt.has_translation("book-a", 0))

with open(zh1, "w", encoding="utf-8", newline="") as f:
    f.write(text + "被篡改。\n")
check("正文与旁车错配时不可读", not lt.has_translation("book-a", 0))
with open(zh1, "w", encoding="utf-8", newline="") as f:
    f.write(text)

with open(raw1, "w", encoding="utf-8", newline="") as f:
    f.write("猫がいる。\n\n雪が降る。\n")
check("原文变化时旧译文不可读", not lt.has_translation("book-a", 0))
with open(raw1, "w", encoding="utf-8", newline="") as f:
    f.write("猫がいる。\n\n雨が降る。\n")

partial = lt.chapter_meta_record(
    "book-a", 0, meta, args, text=text, raw_sha=raw_sha,
    tokens_in=100, tokens_out=90, incomplete_paragraphs=[2],
    incomplete_reason="provider_incomplete")
lt.save_json(lt.chapter_meta_path("book-a", 0), partial)
check("partial 旁车允许可读并保留缺失段",
      lt.has_translation("book-a", 0)
      and not lt.has_complete_translation("book-a", 0)
      and partial["status"] == "partial"
      and partial["incomplete_paragraphs"] == [2])

bad_path = lt.chapter_meta_path("book-a", 0)
with open(bad_path, "w", encoding="utf-8") as f:
    f.write("{broken")
check("损坏旁车不会被当成完成", not lt.has_translation("book-a", 0))
lt.save_json(bad_path, record)

print("=" * 66)
print("1b. 写端显式失效：mtime 没变也能看到新内容")
print("=" * 66)
sig_path = put("novels/book-a/raw/0002.txt", "ああああ\n")
h1 = lt._sha256_file(sig_path)
st_before = os.stat(sig_path)
lt.save_text(sig_path, "いいいい\n")          # 同长度、不同内容
# 模拟 exFAT / sdcardfs：写完立刻回读时 mtime 仍是旧值（2 秒粒度）。
os.utime(sig_path, ns=(st_before.st_atime_ns, st_before.st_mtime_ns))
check("save_text 后哈希缓存已失效（mtime 未变也读到新内容）",
      lt._sha256_file(sig_path) != h1)

print("=" * 66)
print("1c. novel.md 增量重建：未变章不重算，override 立即生效")
print("=" * 66)
# book-a 第 1、2 章此刻都有可读译文（第 2 章在上一段翻完）。
lt.rebuild_novel_md("book-a", meta)
counts: list[int] = []
orig_ht = lt.has_translation
lt.has_translation = lambda s, i: (counts.append(i), orig_ht(s, i))[1]
try:
    lt.rebuild_novel_md("book-a", meta)
    second = len(counts)
    md_path = lt.rebuild_novel_md(
        "book-a", meta, override_chapter=1, override_text="覆盖后的第 2 章译文。")
finally:
    lt.has_translation = orig_ht
md = open(md_path, encoding="utf-8").read()
check("第二次重建不重算未变章", second == 0, f"{second} 次校验")
check("override 的正文立即进入 novel.md 且保留其他章",
      "覆盖后的第 2 章译文。" in md and "有猫。" in md)

print("=" * 66)
print("2. 真实翻译链路写旁车与费用")
print("=" * 66)
put("novels/book-a/raw/0001.txt", "少女は笑った。\n\n「行こう。」\n")


def stub_llm(_system, prompt, _model, _temperature, retries=3, role=None):
    import re
    ids = re.findall(r"^#(\d+):", prompt, re.M)
    return ("\n".join(f"#{n}:第{n}段译文。" for n in ids),
            {"prompt_tokens": 111, "completion_tokens": 77,
             "total_tokens": 188})


lt.call_llm = stub_llm
translate_args = argparse.Namespace(
    model="stub-model", temperature=0.3, force=False, dry_run=False,
    allow_missing=False)
ok = lt.translate_chapter("book-a", 1, meta, translate_args)
side2 = lt.load_chapter_meta("book-a", 1)
check("翻译成功写出正文", ok and lt.has_translation("book-a", 1))
check("旁车记录完整、配置与内容哈希",
      side2 and side2["status"] == "complete"
      and len(side2["source_sha256"]) == 64
      and len(side2["content_sha256"]) == 64
      and len(side2["translation_config_hash"]) == 64)
check("旁车记录真实 usage",
      side2 and side2["tokens"] == {"input": 111, "output": 77})
check("旁车记录模型与 prompt 版本",
      side2 and side2["model_id"] == "stub-model"
      and side2["prompt_version"] == lt.PROMPT_VERSION)

print("=" * 66)
print("2b. 命令行转译也写持久任务日志")
print("=" * 66)
put("novels/book-cli/meta.json", json.dumps({
    "work_id": "book-cli", "slug": "book-cli", "source_id": "cli",
    "title": "CLI 测试书",
    "episodes": [{"id": "c1", "title": "第一话"},
                 {"id": "c2", "title": "第二话"}],
    "glossary": {}, "characters": {}, "style": {},
    "progress": {"translated_through": 0, "fetched_through": 2},
}, ensure_ascii=False))
put("novels/book-cli/raw/0000.txt", "一つ目。\n")
put("novels/book-cli/raw/0001.txt", "二つ目。\n")
lt.call_llm = stub_llm
lt.cmd_next(argparse.Namespace(
    slug="book-cli", count=2, from_chapter=None, force=False,
    summary=False, dry_run=False, allow_missing=False,
    model="stub-model", temperature=0.3))
_cli_rec = lnjobs.JobStore(ROOT).latest("book-cli")
check("CLI 生成已完成任务记录",
      _cli_rec and _cli_rec["status"] == "done"
      and _cli_rec["completed_chapters"] == [1, 2]
      and _cli_rec["remaining_chapters"] == [])
check("CLI 两章都有旁车",
      lt.load_chapter_meta("book-cli", 0) is not None
      and lt.load_chapter_meta("book-cli", 1) is not None)

print("=" * 66)
print("2c. 并发原子写不会混写 JSON、也不会共用固定 .tmp")
print("=" * 66)
concurrent_json = os.path.join(ROOT, "data", "concurrent.json")
concurrent_text = os.path.join(ROOT, "data", "concurrent.txt")
write_errors = []
start = threading.Barrier(2)


def concurrent_writer(label: str) -> None:
    try:
        start.wait(timeout=5)
        for n in range(30):
            lt.save_json(concurrent_json, {
                "writer": label, "n": n, "padding": label * 4000,
            })
            lt.save_text(concurrent_text, (label + "\n") * 2000)
    except BaseException as ex:  # noqa: BLE001
        write_errors.append(f"{label}: {type(ex).__name__}: {ex}")


threads = [threading.Thread(target=concurrent_writer, args=(x,))
           for x in ("A", "B")]
for th in threads:
    th.start()
for th in threads:
    th.join(timeout=10)
try:
    concurrent_doc = json.load(open(concurrent_json, encoding="utf-8"))
    json_ok = concurrent_doc.get("writer") in ("A", "B")
except (OSError, ValueError):
    json_ok = False
concurrent_body = open(concurrent_text, encoding="utf-8").read()
text_ok = concurrent_body in (("A\n" * 2000), ("B\n" * 2000))
residual = (
    [p for p in os.listdir(os.path.dirname(concurrent_json))
     if p.startswith("concurrent.json.") and p.endswith(".tmp")]
    + [p for p in os.listdir(os.path.dirname(concurrent_text))
       if p.startswith("concurrent.txt.") and p.endswith(".tmp")]
)
check("并发写 JSON 最终仍是合法完整文档", json_ok)
check("并发写文本最终仍是完整内容", text_ok)
check("并发写不抛异常、不残留临时文件",
      not write_errors and not residual, str(write_errors + residual))

print("=" * 66)
print("2d. --dry-run 是成功路径：不写正文、不建任务")
print("=" * 66)
put("novels/book-dry/meta.json", json.dumps({
    "work_id": "book-dry", "slug": "book-dry", "source_id": "dry",
    "title": "干跑测试", "episodes": [{"id": "d1", "title": "第一话"}],
    "glossary": {}, "characters": {}, "style": {},
    "progress": {"translated_through": 0, "fetched_through": 1},
}, ensure_ascii=False))
put("novels/book-dry/raw/0000.txt", "これは乾いた原文です。\n")
dry_ok = True
try:
    lt.cmd_next(argparse.Namespace(
        slug="book-dry", count=1, from_chapter=None, force=False,
        summary=False, dry_run=True, allow_missing=False,
        model="stub-model", temperature=0.3))
except BaseException as ex:  # noqa: BLE001
    dry_ok = False
    print(f"    {type(ex).__name__}: {ex}")
check("干跑不会以失败状态退出", dry_ok)
check("干跑不写译文章节", not os.path.exists(
    lt.chapter_path("book-dry", 0)))
check("干跑不创建持久任务",
      lnjobs.JobStore(ROOT).latest("book-dry") is None)

print("=" * 66)
print("3. 持久任务：单活、重启、幂等")
print("=" * 66)
store = lnjobs.JobStore(ROOT)
rec = make_job(store, "book-jobs")
check("任务先以 queued 落盘", rec["status"] == "queued"
      and store.active("book-jobs")["job_id"] == rec["job_id"])
blocked = False
try:
    make_job(store, "book-jobs", source="b")
except lnjobs.ActiveJobExists:
    blocked = True
check("同一本书不能有两个有效任务", blocked)

store.update(rec["job_id"], status="running",
             remaining_chapters=[1, 2], chapter_numbers=[1, 2])
first = store.reconcile_startup()
rec1 = store.get(rec["job_id"])
check("重启把 running 改成 interrupted",
      first["changed"] == 1 and rec1["status"] == "interrupted")
stamp1 = rec1["updated_at"]
for _ in range(2):
    again = store.reconcile_startup()
    check("重复启动扫描不再改状态", again["changed"] == 0)
check("三次重启后记录仍唯一且时间不变",
      len([r for r in store.records()
           if r["job_id"] == rec["job_id"]]) == 1
      and store.get(rec["job_id"])["updated_at"] == stamp1)

target = {"from_chapter": 3, "to_chapter": 4}
sources = [{"chapter": 3, "source_sha256": "1" * 64},
           {"chapter": 4, "source_sha256": "2" * 64}]
k1 = lnjobs.idempotency_key(
    slug="book-i", target=target, sources=sources,
    translation_config_hash="f" * 64)
k2 = lnjobs.idempotency_key(
    slug="book-i", target=target, sources=sources,
    translation_config_hash="f" * 64)
k3 = lnjobs.idempotency_key(
    slug="book-i", target=target, sources=sources,
    translation_config_hash="e" * 64)
check("幂等键稳定且区分配置", k1 == k2 and k1 != k3)

print("=" * 66)
print("4. 模型请求期间强杀")
print("=" * 66)
child_code = r"""
import os, sys, json
sys.path.insert(0, sys.argv[1])
import lnjobs
store = lnjobs.JobStore(sys.argv[2])
target = {"from_chapter": 1, "to_chapter": 1}
key = lnjobs.idempotency_key(
    slug="book-killed", target=target,
    sources=[{"chapter": 1, "source_sha256": "a" * 64}],
    translation_config_hash="b" * 64)
rec = store.create(
    slug="book-killed", target=target, model_provider="local",
    model_role="translate", model_id="stub",
    translation_config_hash="b" * 64, idempotency_key=key,
    requested={"count": 1}, source_entries=[])
store.update(rec["job_id"], status="running")
print("IN_MODEL_REQUEST", flush=True)
os._exit(17)
"""
env_child = {k: v for k, v in os.environ.items()
             if not k.startswith("LNTRANS_")}
env_child.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
child = subprocess.run(
    [sys.executable, "-c", child_code, HERE, ROOT],
    env=env_child, capture_output=True, text=True, timeout=20)
check("模型请求中的子进程被强杀", child.returncode == 17,
      str(child.returncode))
store.reconcile_startup()
killed = [r for r in store.records() if r["slug"] == "book-killed"]
check("强杀后重启显示 interrupted",
      len(killed) == 1 and killed[0]["status"] == "interrupted")

print("=" * 66)
print("4b. 正在使用的任务记录损坏：按恢复处理，不是 500")
print("=" * 66)
srv = load_module("lnserve", "lnserve.py")
rec_active = make_job(store, "book-active-corrupt")
store.update(rec_active["job_id"], status="running")
srv.JOBS["book-active-corrupt"] = {
    "slug": "book-active-corrupt", "status": "running",
    "job_id": rec_active["job_id"], "token": 1,
    "heartbeat": time.time(), "at": time.time(), "count": 1,
}
with open(store.path_for(rec_active["job_id"]), "w", encoding="utf-8") as f:
    f.write("{broken")
view = srv.job_view("book-active-corrupt")
check("损坏的活动任务返回 interrupted + read_only（不抛 ContractError）",
      view.get("status") == "interrupted"
      and view.get("read_only") is True
      and view.get("pending_confirmation") is True,
      str({k: view.get(k) for k in ("status", "read_only")}))
blocked_update = False
try:
    store.update(rec_active["job_id"], status="running")
except lnjobs.JobError:
    blocked_update = True
check("损坏记录拒绝继续写入", blocked_update)
store.quarantine(rec_active["job_id"], write=True)
check("隔离损坏记录后健康检查恢复", store.health(refresh=True)["ok"])
srv.JOBS.pop("book-active-corrupt", None)

print("=" * 66)
print("4c. 段级进度只进内存；损坏记录的写入走只读恢复")
print("=" * 66)
srv.jobstore.STORE = store
rec_mem = make_job(store, "book-mem")
srv.JOBS["book-mem"] = {
    "slug": "book-mem", "status": "running", "job_id": rec_mem["job_id"],
    "token": 7, "heartbeat": time.time(), "at": time.time(), "count": 1,
}
path_mem = store.path_for(rec_mem["job_id"])
st0 = os.stat(path_mem).st_mtime_ns
srv._sync_job("book-mem", 7, message="第 1 章 · 段 3/9", done=3,
              translated=9, total=200, targets=[1, 2])
rec_on_disk = json.load(open(path_mem, encoding="utf-8"))
check("段级进度完全不写盘（内存仍然更新）",
      os.stat(path_mem).st_mtime_ns == st0
      and srv.JOBS["book-mem"]["message"] == "第 1 章 · 段 3/9"
      and srv.JOBS["book-mem"]["done"] == 3)
_leaked = [k for k in ("message", "done", "translated", "total", "targets")
           if k in rec_on_disk]
check("内存态字段不污染持久任务记录", not _leaked, str(_leaked))
srv._sync_job("book-mem", 7, status="running", completed_chapters=[1])
rec_on_disk = json.load(open(path_mem, encoding="utf-8"))
check("真正的状态变更仍然持久化",
      rec_on_disk["status"] == "running"
      and rec_on_disk["completed_chapters"] == [1])

rec_bad = make_job(store, "book-bad-mem")
srv.JOBS["book-bad-mem"] = {
    "slug": "book-bad-mem", "status": "running",
    "job_id": rec_bad["job_id"], "token": 8,
    "heartbeat": time.time(), "at": time.time(), "count": 1,
}
with open(store.path_for(rec_bad["job_id"]), "w", encoding="utf-8") as f:
    f.write("{broken")
_raised = None
try:
    srv._sync_job("book-bad-mem", 8, status="running")
except lnjobs.RecoveryRequired as ex:
    _raised = ex
check("损坏记录的写入抛 RecoveryRequired（不是普通 JobError→provider_error）",
      _raised is not None
      and srv.JOBS["book-bad-mem"]["status"] == "interrupted")
store.quarantine(rec_bad["job_id"], write=True)
srv.JOBS.pop("book-mem", None)
srv.JOBS.pop("book-bad-mem", None)
srv.JOBS_READ_ONLY = False
check("slug 只拒绝真正的逃逸形态（允许 book..x）",
      srv._valid_slug("book..x") and not srv._valid_slug("../x")
      and not srv._valid_slug("..") and not srv._valid_slug("a/b"))

print("=" * 66)
print("4d. 活动记录被外部删除：停任务，但不谎报模型失败、不锁整站")
print("=" * 66)
rec_old = make_job(store, "book-gone")
store.update(rec_old["job_id"], status="done", error=None)
rec_gone = make_job(store, "book-gone")
srv.JOBS["book-gone"] = {
    "slug": "book-gone", "status": "running", "job_id": rec_gone["job_id"],
    "token": 9, "heartbeat": time.time(), "at": time.time(), "count": 1,
}
os.remove(store.path_for(rec_gone["job_id"]))
_raised = None
try:
    srv._sync_job("book-gone", 9, status="running")
except lnjobs.JobRecordMissing as ex:
    _raised = ex
check("记录消失抛 JobRecordMissing（RecoveryRequired 子类）",
      _raised is not None and isinstance(_raised, lnjobs.RecoveryRequired)
      and srv.JOBS["book-gone"]["status"] == "interrupted")
check("记录消失不锁死整站任务写入",
      srv.JOBS_READ_ONLY is False and srv._job_recovery_block() is None)
check("记录消失不写「翻译失败」痕迹",
      not srv._read_book("book-gone").get("trans_error"))
view = srv.job_view("book-gone")
check("恢复视图保留 interrupted 与原因（不回退到旧任务）",
      view.get("status") == "interrupted"
      and "记录" in (view.get("error") or "")
      and view.get("pending_confirmation") is True,
      str({k: view.get(k) for k in ("status", "pending_confirmation")}))
# 同书还有一条旧的 done 记录：断言必须真的能抓到「回退到旧任务」——
# 只看 status 是空转（没有旧记录可回退）。job_id 仍指向刚丢失的那条。
check("记录丢失时不回退到同书的旧 done 记录",
      view.get("job_id") == rec_gone["job_id"]
      and (store.get(rec_old["job_id"]) or {}).get("status") == "done",
      f"view={view.get('job_id')} gone={rec_gone['job_id']} old={rec_old['job_id']}")
srv.JOBS.pop("book-gone", None)

print("=" * 66)
print("5. 损坏任务日志进入只读模式，阅读仍可用")
print("=" * 66)
broken = os.path.join(ROOT, "data", "jobs", "broken-log.json")
with open(broken, "w", encoding="utf-8") as f:
    f.write("{not json")
health = store.health(refresh=True)
check("损坏记录被明确列出", health["read_only"]
      and any(x["file"] == "broken-log.json" for x in health["corrupt"]))
blocked = False
try:
    make_job(store, "book-should-not-write")
except lnjobs.RecoveryRequired:
    blocked = True
check("只读模式拒绝创建新任务", blocked)

probe = socket.socket()
probe.bind(("127.0.0.1", 0))
port = probe.getsockname()[1]
probe.close()
env_server = dict(env_child)
env_server.update(
    LNTRANS_DATA_ROOT=ROOT, LNTRANS_LNFINDER=PROFILE,
    LNTRANS_TEST_SERVER="1")
server = subprocess.Popen(
    [sys.executable, os.path.join(HERE, "lnserve.py"),
     "--port", str(port)],
    cwd=HERE, env=env_server, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, text=True)
base = f"http://127.0.0.1:{port}"
ready = False
home_html = ""
for _ in range(100):
    if server.poll() is not None:
        break
    try:
        with urllib.request.urlopen(base + "/", timeout=0.4) as r:
            home_html = r.read().decode("utf-8")
            ready = r.status == 200
        if ready:
            break
    except OSError:
        time.sleep(0.1)
check("任务日志损坏时首页仍可打开", ready,
      f"exit={server.poll()}")
if ready:
    check("只读模式在书架上明确提示",
          "只读恢复模式" in home_html and "broken-log.json" in home_html)
    with urllib.request.urlopen(base + "/api/recovery", timeout=2) as r:
        recovery = json.loads(r.read().decode())
    check("恢复接口报告只读状态", recovery.get("read_only") is True
          and recovery.get("corrupt"))
    req = urllib.request.Request(
        base + "/api/progress",
        data=json.dumps({"slug": "book-a", "chapter": 1}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=2)
        post_code = 200
    except urllib.error.HTTPError as ex:
        post_code = ex.code
    check("坏任务日志不会冻结阅读进度", post_code == 200, str(post_code))
    req = urllib.request.Request(
        base + "/api/translate",
        data=json.dumps({"slug": "book-a", "count": 1}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=2)
        translate_code = 200
    except urllib.error.HTTPError as ex:
        translate_code = ex.code
    check("只读模式只拒绝翻译任务写入",
          translate_code == 503, str(translate_code))
    try:
        with urllib.request.urlopen(
                base + "/api/job?slug=book-a", timeout=2) as r:
            job_code = r.status
    except urllib.error.HTTPError as ex:
        job_code = ex.code
    check("损坏任务不会让任务状态接口 500", job_code == 200, str(job_code))
server.terminate()
try:
    server.wait(timeout=10)
except subprocess.TimeoutExpired:
    server.kill()
    server.wait(timeout=10)

# Quarantine is the explicit, reversible repair path.
dry = store.quarantine("broken-log", write=False)
check("隔离默认干跑不移动文件",
      os.path.exists(broken) and not dry["written"])
store.quarantine("broken-log", write=True)
check("--write 后损坏文件进入 quarantine",
      not os.path.exists(broken)
      and os.path.exists(os.path.join(ROOT, "data", "jobs", "quarantine")))
check("隔离后日志恢复可写", store.health(refresh=True)["ok"])

print()
if fails:
    print(f"失败 {len(fails)} 项：{fails}")
    print(f"保留现场：{TMP}")
    sys.exit(1)
shutil.rmtree(TMP, ignore_errors=True)
print("章节旁车、持久任务、中断恢复与日志损坏保护全部通过")
