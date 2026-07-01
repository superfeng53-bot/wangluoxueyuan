"""
FastAPI Web 控制台。
复制到 <svc>/web/app.py，替换：
  <SVC>      包名（如 sww_service）
  <PLATFORM> 平台中文名（如 双卫网）
  store / orchestrator / excel_io 均从外部注入（由 run_service.py 传入）。

mount 方式：在 run_service.py 的 lifespan 中初始化 store/orchestrator，
然后 app.state.store = store; app.state.orch = orch。
"""
from __future__ import annotations

import json
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ..credential_parser import CredentialParseError, parse_combined_credentials
from ..error_log import build_error_log_text
from ..runtime import project_root
from ..year_sync import sync_account_years

PLATFORM = "成都职业培训网络学院"
LOGO_LETTER = "网"

_HERE = Path(__file__).parent


def _resolve_templates_dir() -> Path:
    """开发态与 PyInstaller 单文件均可定位 index.html。"""
    candidates = [
        _HERE / "templates",
        project_root() / "wlxy_svc" / "web" / "templates",
    ]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        candidates.insert(0, meipass / "wlxy_svc" / "web" / "templates")
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return _HERE / "templates"


_TEMPLATES_DIR = _resolve_templates_dir()

app = FastAPI(title=f"{PLATFORM} 自动化服务")


# ── 依赖注入快捷方式 ──────────────────────────────────────────────────────────

def get_store(request: Request):
    return request.app.state.store


def get_orch(request: Request):
    return request.app.state.orch


def get_session_manager(request: Request):
    sm = getattr(request.app.state, "session_manager", None)
    if sm is None:
        raise HTTPException(503, detail="session_manager 未初始化")
    return sm


def get_excel(request: Request):
    return request.app.state.excel_io


def _site_profile(request: Request) -> str:
    return getattr(request.app.state, "site_profile", "A").upper()


def _has_credit_apply(request: Request) -> bool:
    return bool(getattr(request.app.state, "has_credit_apply", False))


def _credential_input_mode(request: Request) -> str:
    mode = getattr(request.app.state, "credential_input_mode", "split") or "split"
    mode = str(mode).strip().lower()
    return mode if mode in ("split", "combined") else "split"


def _resolve_credentials(
    request: Request,
    *,
    username: str,
    password: str,
    credentials_combined: str = "",
) -> tuple[str, str]:
    user = (username or "").strip()
    pwd = (password or "").strip()
    combined = (credentials_combined or "").strip()
    if user and pwd:
        return user, pwd
    if combined:
        try:
            parsed = parse_combined_credentials(combined)
        except CredentialParseError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        return parsed.username, parsed.password
    if _credential_input_mode(request) == "combined":
        raise HTTPException(400, detail="请输入账号密码（一栏粘贴）")
    raise HTTPException(400, detail="账号和密码为必填")


def _safe_account(d: dict, store=None, *, include_error_log: bool = True) -> dict:
    """从账号 dict 剥掉敏感字段（密码、cookies、卡号密码）。"""
    safe = dict(d)
    safe.pop("password", None)
    extra = json.loads(safe.get("extra_json") or "{}")
    extra.pop("cookies", None)
    extra.pop("card_password", None)
    safe["extra_json"] = json.dumps(extra, ensure_ascii=False)

    status = safe.get("status", "")
    if include_error_log and store and status == "failed":
        runs = store.get_runs(safe["id"], limit=1)
        apply_err = store.latest_apply_error(safe["id"]) if hasattr(store, "latest_apply_error") else ""
        err_log = build_error_log_text(safe, runs=runs, apply_last_error=apply_err)
        safe["error_log_text"] = err_log
    elif include_error_log:
        err_log = extra.get("error_log_text") or ""
        if not err_log and status == "failed" and safe.get("status_msg"):
            err_log = build_error_log_text(safe)
        safe["error_log_text"] = err_log
    else:
        safe.pop("error_log_text", None)
    return safe


# ── 页面 ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(_TEMPLATES_DIR / "index.html", media_type="text/html; charset=utf-8")


# ── 配置（前端 A/B 型与能力开关）──────────────────────────────────────────────

@app.get("/api/config")
async def get_config(request: Request):
    profile = _site_profile(request)
    return {
        "platform": PLATFORM,
        "site_profile": profile,
        "has_credit_apply": _has_credit_apply(request),
        "has_subjects": profile == "A",
        "has_recharge": bool(getattr(request.app.state, "has_recharge", False)),
        "credential_input_mode": _credential_input_mode(request),
    }


# ── 健康检查 ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"ok": True, "platform": PLATFORM, "ts": time.time()}


@app.get("/api/stats")
async def stats(request: Request):
    store = get_store(request)
    orch = get_orch(request)
    counts = store.count_by_status()
    return {
        "counts": counts,
        "active_workers": orch.active_workers,
        "paused": store.is_paused(),
        "concurrency_limit": store.get_concurrency_limit(),
    }


# ── 账号列表 ──────────────────────────────────────────────────────────────────

@app.get("/api/accounts")
async def list_accounts(
    request: Request,
    status: str = "", search: str = "",
    limit: int = 50, offset: int = 0,
    date_from: float = 0, date_to: float = 0,
):
    store = get_store(request)
    orch = get_orch(request)
    items = store.list_accounts(
        status=status, search=search, limit=limit, offset=offset,
        date_from=date_from, date_to=date_to,
    )
    safe_items = [_safe_account(a, store) for a in items]
    counts = store.count_by_status()
    filtered_total = store.count_accounts(
        status=status, search=search,
        date_from=date_from, date_to=date_to,
    )
    return {
        "items": safe_items,
        "total": counts.get("total", 0),
        "filtered_total": filtered_total,
        "limit": limit,
        "offset": offset,
        "counts": counts,
        "active_workers": orch.active_workers,
        "paused": store.is_paused(),
        "concurrency_limit": store.get_concurrency_limit(),
    }


# ── 同步站点项目进度（B′ 型）────────────────────────────────────────────────
# [OPTIONAL:B_prime] 仅 B_prime 画像实现；复制 project_sync.build_project_status

@app.post("/api/accounts/{account_id}/sync-projects")
async def sync_account_projects(account_id: int, request: Request):
    if _site_profile(request) not in ("B_prime",):
        raise HTTPException(400, detail="仅 B′ 项目驱动型支持同步项目")
    # TODO: ensure_session → build_project_status → store.update extra.project_status
    raise HTTPException(501, detail="请实现 project_sync.build_project_status")


# ── 创建账号 ──────────────────────────────────────────────────────────────────

class CreateAccountBody(BaseModel):
    display_name: str = ""
    username: str = ""
    password: str = ""
    credentials_combined: str = ""  # combined 模式：一栏粘贴，服务端二次解析
    requirements: list[dict] = []   # A 型
    target_years: list[str] = []    # B 型
    report_mode: str = "normal"     # B 型
    extra: dict = {}


@app.post("/api/accounts/batch", status_code=201)
async def create_accounts_batch(body: list[CreateAccountBody], request: Request):
    ids: list[int] = []
    for item in body:
        result = await create_account(item, request)
        ids.append(result["id"])
    return {"ids": ids, "count": len(ids)}


@app.post("/api/accounts", status_code=201)
async def create_account(body: CreateAccountBody, request: Request):
    store = get_store(request)
    profile = _site_profile(request)
    username, password = _resolve_credentials(
        request,
        username=body.username,
        password=body.password,
        credentials_combined=body.credentials_combined,
    )
    if store.get_account_by_username(username):
        raise HTTPException(400, detail=f"账号 {username} 已存在")
    extra = dict(body.extra)
    if body.report_mode and body.report_mode != "normal":
        extra["report_mode"] = body.report_mode
    display = body.display_name.strip()
    if profile == "B":
        display = ""  # B 型登录后从站点回填姓名
    elif not display:
        display = username
    acc_id = store.create_account(
        display_name=display,
        username=username,
        password=password,
        requirements_json=json.dumps(body.requirements, ensure_ascii=False),
        target_years_json=json.dumps(body.target_years, ensure_ascii=False),
        extra_json=json.dumps(extra, ensure_ascii=False),
    )
    return {"id": acc_id}


# ── 导入 Excel ────────────────────────────────────────────────────────────────

@app.post("/api/accounts/upload")
async def upload_accounts(request: Request, file: UploadFile = File(...)):
    store = get_store(request)
    excel_io = get_excel(request)
    data = await file.read()
    site_profile = _site_profile(request)
    result = excel_io.parse_import_xlsx(
        data,
        site_profile=site_profile,
        credential_input_mode=_credential_input_mode(request),
    )

    added = skipped = failed = 0
    errors = list(result.errors)
    for row in result.rows:
        if store.get_account_by_username(row.username):
            skipped += 1
            continue
        try:
            store.create_account(
                display_name=row.display_name,
                username=row.username,
                password=row.password,
                requirements_json=json.dumps(row.requirements, ensure_ascii=False),
                target_years_json=json.dumps(row.target_years, ensure_ascii=False),
                extra_json=json.dumps(row.extra, ensure_ascii=False),
            )
            added += 1
        except Exception as exc:
            failed += 1
            errors.append({"row": 0, "reason": f"账号 {row.username} 导入失败：{exc}"})

    err_msgs = [e["reason"] if isinstance(e, dict) else str(e) for e in errors]
    return {"added": added, "skipped": skipped, "failed": failed + result.failed,
            "errors": err_msgs if err_msgs else None}


# ── 账号详情 ──────────────────────────────────────────────────────────────────

@app.get("/api/accounts/{account_id}")
async def get_account(account_id: int, request: Request):
    store = get_store(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")
    if _site_profile(request) == "B":
        try:
            extra, _report = sync_account_years(get_session_manager(request), acc)
            store.update_extra(account_id, extra)
            acc = store.get_account(account_id) or acc
        except Exception:
            pass
    runs = store.get_runs(account_id, limit=30)
    safe = _safe_account(acc, store)
    safe["runs"] = runs
    if _has_credit_apply(request) and hasattr(store, "list_apply_tasks"):
        safe["apply_tasks"] = store.list_apply_tasks(account_id)
    return safe


@app.post("/api/accounts/{account_id}/sync-years")
async def sync_account_year_progress(account_id: int, request: Request):
    if _site_profile(request) != "B":
        raise HTTPException(400, detail="仅 B 型支持年度进度同步")
    store = get_store(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")
    try:
        extra, report = sync_account_years(get_session_manager(request), acc)
    except Exception as exc:
        raise HTTPException(502, detail=f"同步失败: {exc}") from exc
    store.update_extra(account_id, extra)
    return {"ok": True, "report": report, "account": _safe_account(store.get_account(account_id) or acc, store)}


# ── 编辑账号（含编辑重学）────────────────────────────────────────────────────

class PatchAccountBody(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = None
    credentials_combined: str = ""  # 一栏粘贴改密（与 password 二选一）
    requirements: Optional[list[dict]] = None
    target_years: Optional[list[str]] = None
    report_mode: Optional[str] = None
    extra: Optional[dict] = None
    requeue: bool = False


@app.patch("/api/accounts/{account_id}")
async def patch_account(account_id: int, body: PatchAccountBody, request: Request):
    store = get_store(request)
    orch = get_orch(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")

    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    pwd = (body.password or "").strip()
    combined = (body.credentials_combined or "").strip()
    if combined:
        try:
            parsed = parse_combined_credentials(combined)
        except CredentialParseError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        pwd = parsed.password
    if pwd:
        updates["password"] = pwd
    if body.requirements is not None:
        updates["requirements_json"] = json.dumps(body.requirements, ensure_ascii=False)
    if body.target_years is not None:
        updates["target_years_json"] = json.dumps(body.target_years, ensure_ascii=False)

    if body.extra or body.report_mode:
        cur_extra = json.loads(acc.get("extra_json") or "{}")
        if body.extra:
            cur_extra.update(body.extra)
        if body.report_mode is not None:
            cur_extra["report_mode"] = body.report_mode
        updates["extra_json"] = json.dumps(cur_extra, ensure_ascii=False)

    if updates:
        store.update_account(account_id, **updates)

    if body.requeue:
        orch.interrupt_account(account_id)
        store.requeue_account(account_id)

    return {"ok": True}


# ── 删除账号 ──────────────────────────────────────────────────────────────────

@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: int, request: Request):
    store = get_store(request)
    orch = get_orch(request)
    if not store.get_account(account_id):
        raise HTTPException(404, detail="账号不存在")
    orch.interrupt_account(account_id)
    store.delete_account(account_id)
    return {"ok": True}


# ── 购卡 / 充值（可选）────────────────────────────────────────────────────────

class RechargeBody(BaseModel):
    card_no: str
    card_password: str = ""


@app.post("/api/accounts/{account_id}/recharge")
async def recharge_account(account_id: int, body: RechargeBody, request: Request):
    if not getattr(request.app.state, "has_recharge", False):
        raise HTTPException(404, detail="本站未启用购卡/充值")
    store = get_store(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")
    handler = getattr(request.app.state, "recharge_handler", None)
    if handler is None:
        raise HTTPException(
            501,
            detail="购卡功能未配置：请在 run_service.py 设置 app.state.recharge_handler",
        )
    try:
        result = handler(acc, body.card_no, body.card_password)
    except Exception as exc:
        raise HTTPException(500, detail=f"购卡失败：{exc}") from exc
    if isinstance(result, dict):
        return {"ok": bool(result.get("ok", True)), **result}
    return {"ok": True, "message": str(result)}


# ── 重学 ──────────────────────────────────────────────────────────────────────

@app.post("/api/accounts/{account_id}/top")
async def top_account(account_id: int, request: Request):
    store = get_store(request)
    orch = get_orch(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")
    orch.interrupt_account(account_id)
    store.top_account(account_id)
    return {"ok": True}


@app.post("/api/accounts/{account_id}/requeue")
async def requeue_account(account_id: int, request: Request):
    store = get_store(request)
    orch = get_orch(request)
    acc = store.get_account(account_id)
    if not acc:
        raise HTTPException(404, detail="账号不存在")
    orch.interrupt_account(account_id)
    store.requeue_account(account_id)
    return {"ok": True}


# ── 调度器控制 ────────────────────────────────────────────────────────────────

class LimitBody(BaseModel):
    limit: int


@app.post("/api/scheduler/limit")
async def set_limit(body: LimitBody, request: Request):
    store = get_store(request)
    store.set_concurrency_limit(body.limit)
    return {"ok": True, "limit": store.get_concurrency_limit()}


@app.post("/api/scheduler/pause")
async def pause_scheduler(request: Request):
    get_store(request).set_paused(True)
    return {"ok": True, "paused": True}


@app.post("/api/scheduler/resume")
async def resume_scheduler(request: Request):
    get_store(request).set_paused(False)
    return {"ok": True, "paused": False}


# ── Excel 下载 ────────────────────────────────────────────────────────────────

@app.get("/api/template")
async def download_template(request: Request):
    excel_io = get_excel(request)
    site_profile = _site_profile(request)
    data = excel_io.build_template_xlsx(
        site_profile=site_profile,
        credential_input_mode=_credential_input_mode(request),
    )
    filename = f"{PLATFORM}账号模板.xlsx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_encode(filename)}"},
    )


@app.get("/api/export")
async def export_accounts(request: Request):
    store = get_store(request)
    excel_io = get_excel(request)
    site_profile = _site_profile(request)
    accounts = store.list_accounts(limit=10000)
    for acc in accounts:
        runs = store.get_runs(acc["id"], limit=1)
        acc["last_run_result"] = runs[0]["result"] if runs else ""
        apply_err = store.latest_apply_error(acc["id"]) if hasattr(store, "latest_apply_error") else ""
        acc["error_log_text"] = build_error_log_text(acc, runs=runs, apply_last_error=apply_err)
    data = excel_io.build_export_xlsx(
        accounts,
        site_profile=site_profile,
        credential_input_mode=_credential_input_mode(request),
    )
    import datetime
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{PLATFORM}账号导出_{now_str}.xlsx"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_url_encode(filename)}"},
    )


def _url_encode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")
