# 霜雪旧曾谙 · 新站

Astro 静态博客，GitHub Pages 托管。旧站归档在 `../blog/`。

## 本地

```bash
npm install
npm run dev        # http://localhost:4321
npm run build      # 产物在 dist/
```

## 写文章

**主路径：开一条 issue。** 新建 issue，标题即文章标题，正文写 Markdown，图片直接拖进去；打上 `发布` 标签后 `.github/workflows/publish.yml` 会把它转成 `src/content/posts/<slug>.md`、把图片抓进 `public/images/posts/<slug>/`、提交并回执链接，最后关掉 issue。

| 想控制什么 | 怎么写 |
|---|---|
| 文件名 | 正文第一行写 `slug: xv6-cow`；不写则用标题转写，转不出英文时用 `issue-<编号>` |
| 分类 | 打 `分类:技术` / `分类:随笔` 这类标签，冒号后即 category；都不打则「随笔」 |
| 标签 | 其余标签直接进 `tags`，例如 `xv6`、`os` |
| 摘要 | 默认取正文第一段前 70 字 |
| 阅读时长 | 中文 350 字/分钟估算，自动算 |
| 日期 | 取 issue 创建时间（东八区） |

已发布的 issue 改完正文再存一次，会按同一 slug 覆盖原文件；想改文件名就在正文首行改 `slug`。

备选：直接在 `src/content/posts/` 写 Markdown（frontmatter 见 `PLAN.md`），或用 `/admin/`（需要 fine-grained PAT）。

## 改站点信息

`src/site.config.ts` 一个文件管全部：站名、副标题、邮箱、GitHub、giscus、音乐、后台仓库参数。

## 迁移与字体

```bash
python scripts/migrate_legacy.py      # 旧站 JSON -> Markdown
python scripts/build_font.py <字体.otf>  # 按实际用字重做字体子集
```

新增文章若出现新汉字，重跑字体脚本，否则该字回退系统宋体。

## 部署

推 `main` 触发 `.github/workflows/deploy.yml`。仓库名必须是 `Frostsnow35.github.io` 才能拿到根域名。

## 搜索引擎

| 产出 | 来源 |
|---|---|
| `/sitemap.xml` | `src/pages/sitemap.xml.ts`，文章按 `date` 写 lastmod |
| `/feed.xml` | `src/pages/feed.xml.ts`，RSS 2.0 |
| `/og.png` | `python scripts/build_og.py`，1200×630 分享图 |
| 结构化数据 | `Base.astro` 注入 WebSite + Person，文章页追加 BlogPosting + BreadcrumbList |
| 主动推送 | 部署后 `notify` job 跑 `scripts/indexnow.py`，推给 IndexNow（Bing / Yandex / Naver） |

Google 与百度不认 IndexNow：Google 靠 sitemap + 内链自然抓取，百度需在站长平台单独提交（github.io 在中国大陆可抓性差，属已知限制）。
