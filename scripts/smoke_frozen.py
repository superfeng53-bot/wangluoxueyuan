"""
打包产物 smoke test — 复制到项目 scripts/smoke_frozen.py。

在**隔离临时目录**启动 dist/ 单文件，探测 HTTP 与目录写入；失败 exit 1。
开发态 `python run_service.py` 通过 **不能** 替代本脚本。

用法:
  python scripts/smoke_frozen.py
  python scripts/smoke_frozen.py --binary dist/网络学院_06_23.exe
  python scripts/smoke_frozen.py --keep-temp   # 调试：保留临时目录
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT_SEC = 90
POLL_INTERVAL_SEC = 0.5


def _find_default_binary() -> Path:
    dist = ROOT / "dist"
    if not dist.is_dir():
        raise SystemExit(f"dist/ 不存在: {dist}")
    candidates = sorted(dist.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = [p for p in candidates if p.is_file() and not p.name.startswith(".")]
    if not candidates:
        raise SystemExit(f"dist/ 内无打包产物: {dist}")
    return candidates[0]


def _free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "smoke_frozen/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def _wait_endpoint(endpoint_path: Path, timeout_sec: float) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if endpoint_path.is_file():
            try:
                meta = json.loads(endpoint_path.read_text(encoding="utf-8"))
                if meta.get("url"):
                    return meta
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(f"超时 {timeout_sec}s：未生成 {endpoint_path}")


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    p = argparse.ArgumentParser(description="PyInstaller 单文件 smoke test")
    p.add_argument("--binary", type=Path, default=None, help="dist/ 内单文件路径；默认取最新")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    p.add_argument("--keep-temp", action="store_true", help="失败或成功后保留临时目录")
    args = p.parse_args()

    binary_src = (args.binary or _find_default_binary()).resolve()
    if not binary_src.is_file():
        raise SystemExit(f"打包产物不存在: {binary_src}")

    port = _free_port(args.host)
    temp_root = Path(tempfile.mkdtemp(prefix="frozen-smoke-"))
    binary = temp_root / binary_src.name
    print(f"[smoke] 复制到隔离目录: {temp_root}")
    shutil.copy2(binary_src, binary)
    if sys.platform != "win32":
        binary.chmod(binary.stat().st_mode | 0o111)

    proc = subprocess.Popen(
        [str(binary), "--no-browser", "--host", args.host, "--port", str(port)],
        cwd=temp_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    endpoint_path = temp_root / ".run" / "service" / "endpoint.json"
    errors: list[str] = []

    try:
        meta = _wait_endpoint(endpoint_path, args.timeout)
        base = meta["url"].rstrip("/")
        print(f"[smoke] 服务已监听: {base}")

        for path, check in (
            ("/api/health", lambda b: '"ok"' in b and "true" in b.lower()),
            ("/api/config", lambda b: "site_profile" in b),
            ("/", lambda b: len(b) > 200),
        ):
            try:
                status, body = _http_get(f"{base}{path}")
                if status != 200:
                    errors.append(f"GET {path} → HTTP {status}")
                elif not check(body):
                    errors.append(f"GET {path} → 200 但响应体不符合预期")
                else:
                    print(f"[smoke] GET {path} → OK")
            except (urllib.error.URLError, TimeoutError) as exc:
                errors.append(f"GET {path} → {exc}")

        for rel in (".run/service/service.lock", "data"):
            if not (temp_root / rel).exists():
                errors.append(f"缺少目录/文件: {rel}（应在 exe 同目录创建）")
            else:
                print(f"[smoke] 存在: {rel}")

        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            errors.append(f"进程已退出 code={proc.returncode}\n{out[-4000:]}")

    except TimeoutError as exc:
        out = proc.stdout.read() if proc.stdout else ""
        errors.append(f"{exc}\n--- stdout/stderr tail ---\n{out[-4000:]}")
    finally:
        _terminate(proc)

    if errors:
        print("\n[smoke] FAIL:")
        for e in errors:
            print(f"  - {e}")
        if not args.keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)
        else:
            print(f"[smoke] 临时目录保留: {temp_root}")
        return 1

    print("[smoke] PASS — 打包产物在隔离目录运行正常")
    if not args.keep_temp:
        shutil.rmtree(temp_root, ignore_errors=True)
    else:
        print(f"[smoke] 临时目录保留: {temp_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
