#!/usr/bin/env python3
"""旧站导出 JSON -> Astro 内容集合 Markdown。

用法：
    python scripts/migrate_legacy.py

输入：scripts/legacy-export/*.json（旧站 /api/posts/<id> 的原始响应）
输出：src/content/posts/<slug>.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "scripts" / "legacy-export"
OUT = ROOT / "src" / "content" / "posts"


def yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def clean_body(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    # 页面标题单独渲染，正文开头的重复一级标题去掉
    text = re.sub(r"\A#\s+[^\n]*\n+", "", text)
    return re.sub(r"\n{4,}", "\n\n\n", text)


def to_frontmatter(post: dict) -> str:
    tags = post.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = [tags]
    lines = [
        "---",
        f"title: {yaml_str(post.get('title') or '无题')}",
        f"date: {post.get('published_at') or post.get('created_at')}",
        f"category: {yaml_str(post.get('category') or '随笔')}",
        "tags: [" + ", ".join(yaml_str(t) for t in tags) + "]",
        f"excerpt: {yaml_str(post.get('excerpt') or '')}",
        f"readTime: {int(post.get('read_time') or 5)}",
        f"legacyId: {int(post.get('id') or 0)}",
        "---",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(RAW.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        post = payload.get("data", payload)
        slug = post.get("slug") or f"legacy-{post.get('id')}"
        body = clean_body(post.get("content") or "")
        target = OUT / f"{slug}.md"
        target.write_text(to_frontmatter(post) + "\n\n" + body + "\n", encoding="utf-8")
        written += 1
        print(f"{slug:24} {len(body):>6} chars -> {target.relative_to(ROOT)}")
    print(f"\n共 {written} 篇")


if __name__ == "__main__":
    main()
