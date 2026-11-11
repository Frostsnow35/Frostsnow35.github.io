# 霜雪旧曾谙 · 新站

Astro 静态博客，GitHub Pages 托管。旧站归档在 `../blog/`。

## 本地

```bash
npm install
npm run dev        # http://localhost:4321
npm run build      # 产物在 dist/
```

## 写文章

浏览器打开 `/admin/`，填一次 GitHub PAT（fine-grained，只勾本仓库 Contents 读写）即可新建、编辑、传图。提交后 Actions 自动重建。

也可以直接在 `src/content/posts/` 写 Markdown，frontmatter 见 `PLAN.md`。

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
