#!/usr/bin/env python3
"""把一条 GitHub issue 变成一篇文章。

工作流 .github/workflows/publish.yml 调用；也可本地手动跑：
    GH_TOKEN=xxx REPO=owner/name ISSUE=42 python scripts/issue_to_post.py

规则
  作者      -> 必须是仓库所有者本人（author_association == OWNER），否则拒绝
  title     -> 文章标题
  labels    -> 分类（`分类:技术` 取冒号后）与标签（其余标签）
  正文首行  -> 若形如 `slug: xxx` 则据此命名文件，否则用 issue-<编号>
  正文图片  -> 下载到 public/images/posts/<slug>/ ，链接改写成本地路径
  date      -> issue 创建时间
  excerpt   -> 正文第一段，截 70 字
  readTime  -> 中文按 350 字/分钟、英文按 200 词/分钟估算，向下取整但不小于 1
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "src" / "content" / "posts"
MEDIA = ROOT / "public" / "images" / "posts"

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
REPO = os.environ.get("REPO") or "Frostsnow35/Frostsnow35.github.io"
ISSUE = os.environ.get("ISSUE") or ""

SKIP_LABELS = {"发布", "已发布"}
CATEGORY_PREFIX = "分类:"
OWNER = REPO.split("/")[0].lower()

IMG_MD = re.compile(r"!\[([^\]]*)\]\((https?://[^\s)]+)\)")
IMG_HTML = re.compile(r'<img[^>]+src="(https?://[^"]+)"', re.I)
# issue 里拖进去的图片会落在这些域名上
MEDIA_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "user-images.githubusercontent.com",
    "private-user-images.githubusercontent.com",
    "camo.githubusercontent.com",
}


def is_media(url: str) -> bool:
    u = urlparse(url)
    host = u.netloc.lower()
    if host == "github.com":
        return u.path.startswith("/user-attachments/")
    if host in MEDIA_HOSTS:
        return True
    # 旧附件直接落在 S3 桶上
    return host.endswith("githubusercontent.com") or host.endswith(
        "github-production-user-asset-6210df.s3.amazonaws.com"
    )


def api(path: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "issue-to-post",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def slugify(text: str, fallback: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s or fallback


def fetch_remote(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "issue-to-post"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get("Content-Type", "")


EXT_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
}


def download_images(body: str, slug: str) -> str:
    """把正文里指向 GitHub 的图片抓到仓库，返回改写后的正文。"""
    urls: list[str] = []
    for m in IMG_MD.finditer(body):
        if is_media(m.group(2)):
            urls.append(m.group(2))
    for m in IMG_HTML.finditer(body):
        if is_media(m.group(1)):
            urls.append(m.group(1))

    seen: dict[str, str] = {}
    folder = MEDIA / slug
    for i, url in enumerate(dict.fromkeys(urls), start=1):
        try:
            data, ctype = fetch_remote(url)
        except urllib.error.HTTPError as e:
            print(f"  跳过下载失败 {url}: {e.code}")
            continue
        ext = EXT_BY_TYPE.get(ctype.split(";")[0].strip().lower(), "")
        if not ext:
            ext = Path(url.split("?")[0]).suffix or ".png"
        name = f"{i:02d}{ext}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        local = f"/images/posts/{slug}/{name}"
        seen[url] = local
        print(f"  图片 {url} -> {local} ({len(data) // 1024} KB)")

    for remote, local in seen.items():
        body = body.replace(remote, local)
    return body


def plain(text: str) -> str:
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[`*_>#~]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def make_excerpt(body: str) -> str:
    for block in re.split(r"\n\s*\n", body):
        line = block.strip()
        if not line or line.startswith(("#", "!", "<", "|", "```", "---")):
            continue
        text = plain(line)
        if text:
            return text[:70] + ("…" if len(text) > 70 else "")
    return ""


def read_minutes(body: str) -> int:
    text = plain(body)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", text))
    minutes = cjk / 350 + words / 200
    return max(1, math.ceil(minutes))


def find_by_issue(number: str) -> Path | None:
    """找出由这条 issue 生成的文章；手写稿没有 issue 字段，不会被匹配到。"""
    for f in POSTS.glob("*.md"):
        head = f.read_text(encoding="utf-8")[:400]
        m = re.search(r"^issue:\s*(\d+)\s*$", head, re.M)
        if m and m.group(1) == str(number):
            return f
    return None


def main() -> int:
    if not ISSUE:
        print("缺少 ISSUE 环境变量")
        return 1

    issue = api(f"/repos/{REPO}/issues/{ISSUE}")

    # 双保险：工作流的 if 已经在事件层拦过一次，这里按 API 返回的身份再拦一次，
    # 防止手动 workflow_dispatch 拿别人的 issue 编号发东西
    if "pull_request" in issue:
        print("这是 pull request，不是 issue，跳过")
        return 0
    login = (issue.get("user") or {}).get("login", "")
    if issue.get("author_association") != "OWNER" or login.lower() != OWNER:
        print(f"拒绝：issue 作者 {login}（{issue.get('author_association')}）不是仓库所有者 {OWNER}")
        return 1

    labels = [l["name"] for l in issue.get("labels", [])]
    if not any(l in SKIP_LABELS or l == "发布" for l in labels):
        print("issue 未打「发布」标签，跳过")
        return 0

    title = issue["title"].strip()
    body = (issue.get("body") or "").strip()
    # 写成东八区的裸时间（不带时区）：构建机在 UTC，带时区会被再转一次，
    # 凌晨写的文章就会显示成前一天
    created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
    date = created.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S")

    # 正文首行可选的 slug 指令
    slug = ""
    explicit_slug = False
    first, _, rest = body.partition("\n")
    m = re.match(r"^slug:\s*(\S+)\s*$", first.strip(), re.I)
    if m:
        slug = slugify(m.group(1), "")
        explicit_slug = True
        body = rest.lstrip("\n")
    if not slug:
        slug = slugify(title, "")
        if not slug or not re.search(r"[a-z0-9]", slug):
            slug = f"issue-{ISSUE}"

    # 同一条 issue 认的是 issue 编号，不是标题：改了标题就换文件名会多出一篇文章
    existing = find_by_issue(ISSUE)
    if existing and not explicit_slug:
        slug = existing.stem

    category = "随笔"
    tags: list[str] = []
    for label in labels:
        if label in SKIP_LABELS:
            continue
        if label.startswith(CATEGORY_PREFIX):
            category = label[len(CATEGORY_PREFIX) :].strip() or category
        else:
            tags.append(label)

    target = POSTS / f"{slug}.md"
    if target.exists():
        # 只允许同一条 issue 覆盖自己的稿子；否则改标题撞了 slug 会静默吃掉别的文章
        head = target.read_text(encoding="utf-8")[:400]
        m = re.search(r"^issue:\s*(\d+)\s*$", head, re.M)
        if not m or m.group(1) != str(ISSUE):
            owner = f"issue #{m.group(1)}" if m else "手写稿"
            print(
                f"拒绝：{target.relative_to(ROOT)} 已存在（{owner}）。"
                f"请在正文首行改用别的 slug，例如 `slug: {slug}-2`"
            )
            return 1

    body = download_images(body, slug)
    excerpt = make_excerpt(body)
    minutes = read_minutes(body)

    fm = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"date: {date}",
        f"category: {json.dumps(category, ensure_ascii=False)}",
        "tags: [" + ", ".join(json.dumps(t, ensure_ascii=False) for t in tags) + "]",
        f"excerpt: {json.dumps(excerpt, ensure_ascii=False)}",
        f"readTime: {minutes}",
        f"issue: {ISSUE}",
        "---",
        "",
    ]

    POSTS.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(fm) + body + "\n", encoding="utf-8")

    # 显式改了 slug：把旧稿与旧图目录一起搬过去，别留下两份
    if existing and existing != target:
        old_media = MEDIA / existing.stem
        new_media = MEDIA / slug
        if old_media.exists():
            new_media.parent.mkdir(parents=True, exist_ok=True)
            if new_media.exists():
                shutil.rmtree(new_media)
            old_media.rename(new_media)
        existing.unlink()
        print(f"重命名 {existing.name} -> {target.name}")
    slug_file = os.environ.get("SLUG_FILE")
    if slug_file:
        Path(slug_file).write_text(slug, encoding="utf-8")
    print(f"写入 {target.relative_to(ROOT)}（{minutes} 分钟）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
