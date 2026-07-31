#!/usr/bin/env python3
"""Local, dependency-free control center for the SuperMedia asset catalog.

It intentionally binds to 127.0.0.1 only.  The command has two modes:
``update`` performs an atomic operational update, while ``serve`` exposes the
same operation and read-only statistics in a local browser.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from media_asset_catalog import Catalog, canonical_json


APP_NAME = "SuperMedia 资产中心"
DEFAULT_PORT = 8765


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_platforms(root: Path) -> list[str]:
    """Return only channel directories that directly contain creator metadata."""
    return sorted(
        candidate.name
        for candidate in root.iterdir()
        if candidate.is_dir()
        and not candidate.name.startswith(".")
        and any(child.is_file() and child.name == "metadata.tsv" for child in candidate.glob("*/metadata.tsv"))
    )


@contextmanager
def update_lock(lock_path: Path) -> Iterator[None]:
    """A cross-platform non-blocking lock; overlapping catalog writes are unsafe."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                handle.write("0")
                handle.flush()
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("已有资产库更新正在运行，请等待完成后再试") from error
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()


def backup_database(catalog: Catalog) -> Path:
    backups = catalog.state_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backups / f"media_catalog_{stamp}.sqlite"
    backup = sqlite3.connect(destination)
    try:
        catalog.connection.backup(backup)
    finally:
        backup.close()
    return destination


def update_catalog(root: Path) -> dict[str, Any]:
    """Back up, incrementally sync every real platform, audit, and export reports."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Video_Download 根目录不存在: {root}")
    state_dir = root / ".supermedia"
    with update_lock(state_dir / "update.lock"):
        catalog = Catalog(root)
        try:
            backup = backup_database(catalog)
            platforms = discover_platforms(root)
            if not platforms:
                raise ValueError("未发现包含博主 metadata.tsv 的渠道目录")
            sync_stats = {platform: catalog.sync_platform(platform) for platform in platforms}
            audit = catalog.audit()
            reports = catalog.export_reports()
            result = {
                "status": "ok" if audit["status"] == "ok" else "audit_error",
                "updated_at": utc_now(),
                "root": str(root),
                "platforms": platforms,
                "sync": sync_stats,
                "backup": str(backup),
                "audit": audit,
                "reports": reports,
                "summary": catalog.summary(),
            }
            report_path = state_dir / "reports" / "last_update.json"
            report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return result
        finally:
            catalog.close()


def dashboard(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    catalog = Catalog(root)
    try:
        summary = catalog.summary()
        rows = catalog.connection.execute(
            """
            SELECT c.platform, c.canonical_creator AS creator,
                   COUNT(DISTINCT csi.source_key) AS source_count,
                   COUNT(DISTINCT CASE WHEN loc.role='derivative' THEN loc.asset_id END) AS derivative_count,
                   COUNT(DISTINCT p.publication_id) AS publication_count
            FROM creators c
            LEFT JOIN creator_source_inventory csi ON csi.creator_key=c.creator_key
            LEFT JOIN asset_lineage al ON al.source_key=csi.source_key
            LEFT JOIN asset_locations loc ON loc.asset_id=al.asset_id AND loc.present=1
            LEFT JOIN publications p ON p.source_key=csi.source_key
            GROUP BY c.creator_key
            ORDER BY publication_count DESC, source_count DESC, creator
            """
        ).fetchall()
        warnings = catalog.connection.execute(
            """
            SELECT w.warning_id, w.code, w.asset_id, w.message, w.created_at,
                   GROUP_CONCAT(loc.path, ' | ') AS paths
            FROM warnings w
            LEFT JOIN asset_locations loc ON loc.asset_id=w.asset_id AND loc.present=1
            WHERE w.status='open'
            GROUP BY w.warning_id
            ORDER BY w.severity DESC, w.created_at ASC
            LIMIT 200
            """
        ).fetchall()
        recent = catalog.connection.execute(
            """
            SELECT account_key, title, status, updated_at
            FROM publications ORDER BY updated_at DESC LIMIT 12
            """
        ).fetchall()
        report_path = catalog.state_dir / "reports" / "last_update.json"
        last_update = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
        return {
            "summary": summary,
            "creators": [dict(row) for row in rows],
            "warnings": [dict(row) for row in warnings],
            "recent_publications": [dict(row) for row in recent],
            "last_update": last_update,
        }
    finally:
        catalog.close()


def link_lineage(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(payload.get("file") or "")).expanduser()
    source = str(payload.get("source_key") or "").strip()
    evidence = str(payload.get("evidence") or "").strip()
    if not path.is_file() or not source or len(evidence) < 8:
        raise ValueError("需提供存在的文件、source_key 和至少 8 个字符的核验依据")
    try:
        confidence = float(payload.get("confidence", 1.0))
    except (TypeError, ValueError) as error:
        raise ValueError("confidence 必须是 0 到 1 的数字") from error
    catalog = Catalog(root)
    try:
        return catalog.link_asset(path, source, batch_id=payload.get("batch_id"), evidence=evidence, confidence=confidence)
    finally:
        catalog.close()


HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuperMedia 资产中心</title>
<style>
:root{--ink:#19251d;--paper:#f5f0e5;--card:#fffdf7;--green:#0d5c3a;--acid:#d9ed54;--red:#b83a2f;--muted:#738078;--line:#d8d1c3}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px Menlo,Consolas,monospace}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.18;background-image:linear-gradient(#1d2 1px,transparent 1px),linear-gradient(90deg,#1d2 1px,transparent 1px);background-size:44px 44px;mask-image:linear-gradient(to bottom,black,transparent 75%)}header{padding:32px max(4vw,24px) 25px;border-bottom:1px solid var(--ink);display:flex;gap:24px;align-items:end;justify-content:space-between;position:relative}h1{font:900 clamp(32px,5vw,68px)/.92 'Bodoni 72','Songti SC',serif;margin:0;letter-spacing:-.09em}h1 small{font:500 11px Menlo,Consolas,monospace;letter-spacing:.08em;display:block;margin:13px 0 0 6px;color:var(--green)}button{font:500 13px Menlo,Consolas,monospace;background:var(--acid);border:1px solid var(--ink);padding:13px 17px;cursor:pointer;box-shadow:4px 4px 0 var(--ink)}button:hover{transform:translate(2px,2px);box-shadow:2px 2px 0 var(--ink)}button:disabled{opacity:.5;cursor:wait}main{max-width:1440px;margin:auto;padding:30px max(4vw,24px) 60px}.status{color:var(--muted);min-height:22px}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:25px 0}.kpi{border:1px solid var(--line);background:var(--card);padding:15px;min-height:116px}.kpi b{font:900 35px/1 'Bodoni 72','Songti SC',serif;display:block;margin-top:16px}.kpi.alert{border-color:var(--red);color:var(--red)}section{background:var(--card);border:1px solid var(--line);margin-top:18px;padding:20px}h2{font:900 24px 'Bodoni 72','Songti SC',serif;margin:0 0 16px;letter-spacing:-.06em}table{width:100%;border-collapse:collapse}th{text-align:left;font-size:11px;color:var(--muted);font-weight:400}td,th{padding:11px 8px;border-bottom:1px solid #e9e2d6;vertical-align:top}.warning{color:var(--red)}.small{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:1.4fr .6fr;gap:18px}.hidden{display:none}dialog{border:1px solid var(--ink);box-shadow:9px 9px 0 var(--ink);background:var(--card);padding:25px;max-width:650px;width:calc(100% - 32px)}dialog::backdrop{background:#19251d99}label{display:block;margin:12px 0 5px}input,textarea{width:100%;font:13px Menlo,Consolas,monospace;padding:9px;border:1px solid var(--line);background:#fff}textarea{height:90px}.dialog-actions{margin-top:18px;display:flex;gap:16px;justify-content:end}.plain{background:var(--card);box-shadow:none}@media(max-width:800px){header{align-items:start;flex-direction:column}.kpis{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}table{font-size:12px}th:nth-child(n+4),td:nth-child(n+4){display:none}}
</style>
<header><div><h1>资产中心<small>SUPERMEDIA / LOCAL-ONLY</small></h1></div><div><button id="update">↻ 一键更新资产库</button><div class="status" id="status"></div></div></header>
<main><div class="kpis" id="kpis"></div><div class="grid"><section><h2>博主资产地图</h2><table><thead><tr><th>渠道 / 博主</th><th>原始作品</th><th>衍生成品</th><th>发布记录</th></tr></thead><tbody id="creators"></tbody></table></section><section><h2>上次更新</h2><div id="last" class="small">尚未运行一键更新</div><h2 style="margin-top:25px">最近发布</h2><div id="recent" class="small"></div></section></div><section><h2>待人工确认（HOLD）</h2><p class="small">未知或多重来源的资产不会进入上传计划。先在代表帧、文件路径和原始作品间核验，再补充血缘。</p><table><thead><tr><th>原因</th><th>文件</th><th>提示</th><th></th></tr></thead><tbody id="warnings"></tbody></table></section></main>
<dialog id="linkDialog"><form method="dialog" id="linkForm"><h2>补全资产血缘</h2><p class="small">此操作会解除该文件的 HOLD；请只在人工核验来源后提交。</p><label>文件绝对路径</label><input name="file" required><label>来源 ID（如 instagram:DaBCJx9CdIU）</label><input name="source_key" required><label>核验依据</label><textarea name="evidence" required placeholder="例如：代表帧比对、历史处理报告、原片序号…"></textarea><label>处理批次（可选）</label><input name="batch_id"><div class="dialog-actions"><button type="button" class="plain" onclick="linkDialog.close()">取消</button><button>确认关联</button></div></form></dialog>
<script>
const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let data;
function metric(name,value,alert=false){return `<div class="kpi ${alert?'alert':''}"><span>${name}</span><b>${value??0}</b></div>`}
async function load(){data=await fetch('/api/dashboard').then(r=>r.json());const s=data.summary;$('#kpis').innerHTML=[metric('博主',s.counts.creators),metric('源作品',s.counts.creator_source_inventory),metric('资产文件',s.counts.assets),metric('发布记录',s.counts.publications),metric('HOLD',s.open_blocking_warnings,true)].join('');$('#creators').innerHTML=data.creators.map(x=>`<tr><td>${esc(x.platform)} / <b>${esc(x.creator)}</b></td><td>${x.source_count}</td><td>${x.derivative_count}</td><td>${x.publication_count}</td></tr>`).join('')||'<tr><td colspan="4">暂无数据</td></tr>';$('#warnings').innerHTML=data.warnings.map(x=>`<tr><td class="warning">${esc(x.code)}</td><td class="small">${esc(x.paths||'未找到现存路径')}</td><td class="small">${esc(x.message)}</td><td><button class="plain" onclick="openLink('${esc(x.paths||'')}')">关联来源</button></td></tr>`).join('')||'<tr><td colspan="4">没有待处理项</td></tr>';$('#recent').innerHTML=data.recent_publications.map(x=>`<p>${esc(x.account_key)}<br>${esc(x.title||'未命名')} · ${esc(x.status)}</p>`).join('')||'暂无发布记录';const u=data.last_update;$('#last').innerHTML=u?`完成：${esc(u.updated_at)}<br>渠道：${esc((u.platforms||[]).join(', '))}<br>备份：${esc(u.backup)}`:'尚未运行一键更新';}
function openLink(path){$('#linkForm [name=file]').value=path||'';$('#linkDialog').showModal()}window.openLink=openLink;
$('#update').onclick=async()=>{const b=$('#update');b.disabled=true;$('#status').textContent='正在备份、扫描、审计并生成报表…';try{const r=await fetch('/api/update',{method:'POST'});const v=await r.json();if(!r.ok)throw Error(v.error);$('#status').textContent='更新完成：'+v.summary.counts.assets+' 个资产';await load()}catch(e){$('#status').textContent='更新失败：'+e.message}finally{b.disabled=false}};
$('#linkForm').onsubmit=async e=>{e.preventDefault();const p=Object.fromEntries(new FormData(e.target));try{const r=await fetch('/api/lineage/link',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(p)});const v=await r.json();if(!r.ok)throw Error(v.error);$('#linkDialog').close();$('#status').textContent='血缘已关联：'+v.source_key;await load()}catch(err){alert('关联失败：'+err.message)}};load().catch(e=>$('#status').textContent='读取失败：'+e.message);
</script>'''


class Handler(BaseHTTPRequestHandler):
    root: Path

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = canonical_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/api/dashboard":
            try:
                self.send_json(HTTPStatus.OK, dashboard(self.root))
            except (OSError, ValueError, sqlite3.Error) as error:
                self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
            return
        if urlparse(self.path).path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            if route == "/api/update":
                self.send_json(HTTPStatus.OK, update_catalog(self.root))
                return
            if route == "/api/lineage/link":
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json(HTTPStatus.OK, link_lineage(self.root, payload))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except RuntimeError as error:
            self.send_json(HTTPStatus.CONFLICT, {"error": str(error)})
        except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def serve(root: Path, port: int, open_browser: bool) -> None:
    Handler.root = root.expanduser().resolve()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"{APP_NAME} 已启动：{url}")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--root", required=True, type=Path, help="Video_Download 根目录")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("update", help="备份、同步、审计、导出报表")
    serve_parser = commands.add_parser("serve", help="启动本地浏览器管理台")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument("--open", action="store_true", help="启动后打开默认浏览器")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "update":
            print(json.dumps(update_catalog(args.root), ensure_ascii=False, indent=2))
            return 0
        serve(args.root, args.port, args.open)
        return 0
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as error:
        print(f"资产中心错误：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
