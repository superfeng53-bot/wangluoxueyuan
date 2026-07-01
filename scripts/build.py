"""PyInstaller 单文件打包入口。"""
from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_NAME = "网络学院"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--clean", action="store_true")
    args = p.parse_args()

    if args.clean:
        for d in ("build", "dist"):
            shutil.rmtree(ROOT / d, ignore_errors=True)

    today = datetime.datetime.now()
    suffix = f"{today.month:02d}_{today.day:02d}"
    binary_name = f"{SITE_NAME}_{suffix}"

    spec_template = (ROOT / "scripts" / "wlxy.spec.template").read_text(encoding="utf-8")
    spec = spec_template.replace("{{BINARY_NAME}}", binary_name)
    spec_path = ROOT / "scripts" / f".{binary_name}.spec"
    spec_path.write_text(spec, encoding="utf-8")

    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_path)],
    )
    ext = ".exe" if sys.platform == "win32" else ""
    binary_path = ROOT / "dist" / f"{binary_name}{ext}"
    print(f"\nBuilt: {binary_path}")

    smoke = ROOT / "scripts" / "smoke_frozen.py"
    if smoke.is_file():
        print("\nRunning packaged artifact smoke test …")
        subprocess.check_call([sys.executable, str(smoke), "--binary", str(binary_path)])
    else:
        raise SystemExit(
            "缺少 scripts/smoke_frozen.py — 从 templates/code/scripts/ 复制。"
            "未通过打包 smoke 不得宣布阶段 6 完成。"
        )


if __name__ == "__main__":
    main()
