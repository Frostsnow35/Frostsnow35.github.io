#!/usr/bin/env python3
"""部署完成后把 sitemap 里的全部 URL 推给 IndexNow（Bing / Yandex / Naver / Seznam）。

用法：
    python3 scripts/indexnow.py            # 读 indexnow.key，抓线上 sitemap 再提交
    python3 scripts/indexnow.py --dry-run  # 只打印将要提交的 URL

IndexNow 不覆盖 Google 与百度：Google 靠 sitemap + 内链，百度要在站长平台单独提交。
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "frostsnow35.github.io"
SITEMAP = f"https://{HOST}/sitemap.xml"
ENDPOINT = "https://api.indexnow.org/indexnow"


def fetch_sitemap(attempts: int = 8, wait: int = 15) -> str:
    last: Exception | None = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(SITEMAP, timeout=20) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"sitemap 第 {i + 1} 次抓取失败：{e}，{wait}s 后重试")
            time.sleep(wait)
    raise SystemExit(f"抓不到 sitemap：{last}")


def main() -> None:
    key = (ROOT / "indexnow.key").read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit("indexnow.key 为空")

    xml = fetch_sitemap()
    urls = re.findall(r"<loc>(.*?)</loc>", xml)
    if not urls:
        raise SystemExit("sitemap 里没有 URL")

    if "--dry-run" in sys.argv:
        print(f"{len(urls)} 个 URL：")
        for u in urls:
            print(" ", u)
        return

    payload = {
        "host": HOST,
        "key": key,
        "keyLocation": f"https://{HOST}/{key}.txt",
        "urlList": urls,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"IndexNow {r.status}，提交 {len(urls)} 个 URL")
    except urllib.error.HTTPError as e:
        # 200/202 为接受；其余状态码代表密钥或格式问题
        raise SystemExit(f"IndexNow 返回 {e.code}：{e.read().decode('utf-8', 'replace')[:300]}")


if __name__ == "__main__":
    main()
