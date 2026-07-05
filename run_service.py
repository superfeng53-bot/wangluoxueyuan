"""成都职业培训网络学院 — 多账号常驻服务入口。"""
from __future__ import annotations

import argparse
import json
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from wlxy_api.session_manager import get_session_manager
from wlxy_svc.config import SERVICE_PORT, SITE_PROFILE
from wlxy_svc.orchestrator import Orchestrator
from wlxy_svc.persistence.store import Store
from wlxy_svc.runtime import (
    SingleInstanceLock,
    clear_endpoint_meta,
    find_available_port,
    open_existing_ui,
    project_root,
    write_endpoint_meta,
)
from wlxy_svc.web import excel_io
from wlxy_svc.web.app import app
from wlxy_svc.worker import AccountWorker

DEFAULT_PORT = SERVICE_PORT
CREDENTIAL_INPUT_MODE = "combined"  # 回退默认；优先读 data/account.json
HAS_CREDIT_APPLY = False
HAS_RECHARGE = False


def _resolve_credential_input_mode(root: Path, cli_mode: str = "") -> str:
    """优先 CLI > data/account.json > CREDENTIAL_INPUT_MODE 常量。"""
    mode = (cli_mode or "").strip().lower()
    if mode in ("split", "combined"):
        return mode
    account_path = root / "data" / "account.json"
    if account_path.is_file():
        try:
            data = json.loads(account_path.read_text(encoding="utf-8"))
            mode = str(data.get("credential_input_mode", "")).strip().lower()
            if mode in ("split", "combined"):
                return mode
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    mode = str(CREDENTIAL_INPUT_MODE or "split").strip().lower()
    return mode if mode in ("split", "combined") else "split"


def main() -> int:
    p = argparse.ArgumentParser(description="启动成都职业培训网络学院自动化服务")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument(
        "--credential-input-mode",
        choices=("split", "combined"),
        default="",
        help="凭证输入模式：split=账号密码分两栏，combined=一栏粘贴自动识别（默认读 data/account.json）",
    )
    args = p.parse_args()

    root = project_root()
    svc_dir = root / ".run" / "service"
    svc_dir.mkdir(parents=True, exist_ok=True)
    lock_path = svc_dir / "service.lock"
    endpoint_path = svc_dir / "endpoint.json"

    lock = SingleInstanceLock(lock_path)
    if not lock.try_acquire():
        open_existing_ui(endpoint_path, no_browser=args.no_browser)
        return 0

    db_path = root / "data" / "service.db"
    store = Store(db_path)
    store.ensure_scheduler_defaults()
    store.startup_recovery()

    session_manager = get_session_manager()

    def worker_factory(account, cancel_event=None):
        return AccountWorker(
            account,
            store=store,
            session_manager=session_manager,
            site_profile=SITE_PROFILE,
            cancel_event=cancel_event,
            has_credit_apply=HAS_CREDIT_APPLY,
        )

    orch = Orchestrator(store, worker_factory=worker_factory, apply_worker=None)
    orch.start()

    app.state.store = store
    app.state.orch = orch
    app.state.session_manager = session_manager
    app.state.excel_io = excel_io
    app.state.site_profile = SITE_PROFILE
    app.state.has_credit_apply = HAS_CREDIT_APPLY
    app.state.has_recharge = HAS_RECHARGE
    app.state.credential_input_mode = _resolve_credential_input_mode(
        root, args.credential_input_mode,
    )
    app.state.recharge_handler = None

    port = find_available_port(args.host, args.port)
    url = f"http://{args.host}:{port}"
    write_endpoint_meta(endpoint_path, args.host, port)

    try:
        if not args.no_browser:
            def _open() -> None:
                time.sleep(1.5)
                webbrowser.open(url)

            threading.Thread(target=_open, daemon=True).start()
        uvicorn.run(app, host=args.host, port=port, log_level="info")
    finally:
        orch.stop()
        clear_endpoint_meta(endpoint_path)
        lock.release()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        import sys
        import traceback

        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("启动失败，按 Enter 退出…")
        raise
