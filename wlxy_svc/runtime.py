"""
服务运行时工具：单实例锁、端口探测、endpoint.json 读写。
完整通用，直接复制到 <svc>/runtime.py，无需修改。
"""
from __future__ import annotations

import json
import socket
import sys
import webbrowser
from pathlib import Path
from typing import Optional


def project_root() -> Path:
    """开发时 = 仓库根（本文件往上两级）；PyInstaller 单文件 = exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# ── 单实例锁 ─────────────────────────────────────────────────────────────────

class SingleInstanceLock:
    """
    非阻塞文件锁。
    POSIX: fcntl.flock   Windows: msvcrt.locking（降级到 lockfile）
    """

    def __init__(self, lock_path: Path) -> None:
        self._path = lock_path
        self._fh: Optional[object] = None

    def try_acquire(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self._path, "w")
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            if self._fh:
                self._fh.close()
                self._fh = None
            return False

    def release(self) -> None:
        if self._fh:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            finally:
                self._fh.close()
                self._fh = None


# ── 端口探测 ──────────────────────────────────────────────────────────────────

def find_available_port(host: str, start_port: int, max_tries: int = 50) -> int:
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available port found in [{start_port}, {start_port + max_tries})")


# ── endpoint.json ─────────────────────────────────────────────────────────────

def write_endpoint_meta(path: Path, host: str, port: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"http://{host}:{port}"
    path.write_text(
        json.dumps({"host": host, "port": port, "url": url, "pid": __import__("os").getpid()}),
        encoding="utf-8",
    )


def clear_endpoint_meta(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def open_existing_ui(endpoint_path: Path, *, no_browser: bool) -> None:
    try:
        meta = json.loads(endpoint_path.read_text(encoding="utf-8"))
        url = meta.get("url", "")
        if url and not no_browser:
            webbrowser.open(url)
    except Exception:
        pass
