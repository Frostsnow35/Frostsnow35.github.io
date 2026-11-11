#!/usr/bin/env python3
"""按站点实际用到的字符裁剪思源宋体，产物约 200KB。

用法：
    python scripts/build_font.py <源字体.otf>

每次新增文章、且文章标题/正文里出现新汉字时重跑一次即可；
漏字会自动回退到系统宋体，不会出现豆腐块。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "fonts" / "serif-sc.woff2"
SCAN_DIRS = [ROOT / "src"]
EXTS = {".md", ".astro", ".ts", ".html"}
BASE = (
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    " .,:;!?'\"()[]{}<>/\\|+-*=#@&%$~`^_"
    "，。、；：？！“”‘’（）《》【】—…·×÷≤≥→←↑↓"
)


def collect() -> str:
    chars = set(BASE)
    for folder in SCAN_DIRS:
        for path in folder.rglob("*"):
            if path.suffix in EXTS:
                chars.update(path.read_text(encoding="utf-8", errors="ignore"))
    chars = {c for c in chars if c.isprintable() and c != "\n"}
    return "".join(sorted(chars))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    src = Path(sys.argv[1])
    text = collect()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    work = ROOT / ".fontwork"
    work.mkdir(exist_ok=True)
    text_file = work / "chars.txt"
    text_file.write_text(text, encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "fontTools.subset",
        str(src),
        f"--text-file={text_file}",
        "--flavor=woff2",
        "--layout-features=*",
        "--no-hinting",
        "--desubroutinize",
        f"--output-file={OUT}",
    ]
    subprocess.run(cmd, check=True)
    kb = OUT.stat().st_size / 1024
    print(f"{len(text)} 字符 -> {OUT.relative_to(ROOT)}  {kb:.0f} KB")


if __name__ == "__main__":
    main()
