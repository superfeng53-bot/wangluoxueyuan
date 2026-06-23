"""B 型站点请使用 run_year.py；本入口仅作提示。"""
import sys

print(
    "本站点为 B 型（公需年度），请使用 run_year.py：\n"
    "  python run_year.py --account data/account.json --years 2026 --probe-progress\n"
    "  python run_year.py --account data/account.json --years 2026",
    file=sys.stderr,
)
sys.exit(2)
