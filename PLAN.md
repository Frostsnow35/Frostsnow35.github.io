# 新站方案

旧站 `blog/`（Vue3 + Flask + Supabase + 26 个页面）保留为归档，不再维护。
新站 `blog-v2/`，Astro 静态构建，GitHub Pages 托管。

## 一、边界

| 做 | 不做 |
|---|---|
| 文章阅读、按年归档 | 相册、电影收藏、音乐收藏、宝藏、友链、Uptime |
| 关于页、留言板、站内音乐 | 搜索、RSS、TOC、评论、统计、点赞、阅读量 |
| 浏览器内写文章、发图 | 富文本、草稿版本管理、多人协作 |

砍掉的模块不是"以后再说"，是"没有"。极简站的成本不在于功能少，而在于每个功能都要占一块视觉预算。

## 二、路由

| 路径 | 页面 | 说明 |
|---|---|---|
| `/` | 首屏 + 文章流 | 全屏色场 + 6 篇文章列表 |
| `/posts/` | 归档 | 按年分组 |
| `/posts/<slug>/` | 文章 | 正文列宽 46rem |
| `/about/` | 关于 | |
| `/guestbook/` | 留言 | giscus |
| `/admin/` | 后台 | `robots.txt` 已屏蔽 |
| `/post/<slug>/` | 旧地址 | meta refresh + canonical 指向新地址 |

旧站 `/home`、`/category`、`/tag`、`/treasure/*` 不做跳转，直接 404。

## 三、视觉系统

### 色彩

| 角色 | 亮色（默认） | 暗色 |
|---|---|---|
| 纸 | `#F6F3EC` | `#0E1012` |
| 墨 | `#16181C` | `#ECE7DD` |
| 爱马仕橙 | `#FF6A00` | `#FF7A1A` |
| 海蓝 | `#3CC3E8` | `#3FC6EA` |
| 海蓝衬底 | `rgba(60,195,232,.11)` | `rgba(63,198,234,.09)` |

色场：`linear-gradient(101deg, #F5811F 0%, … #3CC3E8 100%)`，中间由两色自然混出灰绿过渡。

### 撞色纪律

橙色是**画面层级**，不是元素装饰。允许出现的位置只有四处：年份标签、当前导航圆点、hover 态下划线/序号、后台主按钮。单屏面积 ≤ 5%。

海蓝是**衬底**，只出现在三处：代码块、引用块、首页的那一条 about 色带。它不下到正文字色上。

大面积撞色只发生在色场：首屏整屏渐变、关于页 46vh 头部。两处都不相邻，中间隔着暖白正文区。

### 无边界规则

- 无卡片、无圆角（除头像）、无阴影、无投影
- 分区靠色场硬切，不靠描边和分割线
- 列表行之间只有 1px 线，且透明度 14%，退到视觉底层
- 导航透明悬浮，不占布局

### 字体

| 用途 | 字体 | 体积 |
|---|---|---|
| 标题、关于页导语 | 思源宋体 CN Regular（子集） | 215 KB / 1080 字 |
| 正文、UI | 系统无衬线（PingFang SC / 微软雅黑） | 0 |
| 日期、序号、标签 | JetBrains Mono → SF Mono → Consolas | 0 |

子集由 `scripts/build_font.py` 扫描 `src/` 实际用字生成，新增文章出现新汉字时重跑。漏字自动回退系统宋体，不会出豆腐块。

### 动效

| 效果 | 参数 | 位置 |
|---|---|---|
| 下划线生长 | `scaleX(0→1)`，420ms | 正文内链接 |
| 行微移 | 标题右移 14px + 序号变橙 | 文章列表 hover |
| 磁吸 | 指针偏移 1/40，上限 6px | 首屏"滚动进入" |
| 入场 | 上移 14px + 淡入 | 首屏文案，分段 0.1/0.16/0.34s 延迟 |
| 滚动显现 | `animation-timeline: view()` | 关于页段落、色带 |
| 音量淡入 | 0→0.4，900ms | 首次交互后 |

全部走 CSS，无 GSAP、无 Three.js、无自定义光标。`prefers-reduced-motion` 下全部关停。

## 四、内容模型

`src/content/posts/*.md`，文件名即 slug：

```yaml
title: string
date: ISO8601
category: string      # 技术 / 随笔
tags: string[]
excerpt: string
readTime: number
legacyId?: number     # 旧站主键，仅供追溯
```

不设分类页和标签页。6 篇文章做分类页是给空房间装走廊；等文章过 30 篇再议。

## 五、迁移结果

源：`https://frostsnow-blog.viddy.de5.net/api/posts/<id>`，6 篇已全量导出。

| slug | 标题 | 正文字数 | 说明 |
|---|---|---|---|
| xv6-mmap | xv6-mmap | 11,370 | |
| xv6-filesystem-2 | xv6-filesystem | 8,775 | 旧站 slug 带 `-2`，沿用 |
| xv6-locking | xv6-locking | 9,275 | |
| xv6nd | xv6实验-网络驱动 | 8,109 | |
| xv6cow | xv6实验-COW | 6,318 | |
| post-93e70e96 | 我的第一篇文章 | 115 | |

清洗规则：去正文开头重复的一级标题，合并 3 个以上连续空行。
原始 JSON 留在 `scripts/legacy-export/`，`scripts/migrate_legacy.py` 可重跑。

未迁移：留言 0 条、相册 0 个、封面图 0 张，均为空集，无需处理。
唯一媒体是 `eikyuu hours.mp3`（5.0 MB）与 `avatar.jpg`，已复制到 `public/`。

## 六、写作链路

`/admin/` 是纯前端页面，直连 GitHub REST API：

1. 填一次 fine-grained PAT（只授权本仓库 `Contents: Read and write`），存本机 localStorage
2. 选文件或新建，编辑 frontmatter 字段与 Markdown 正文
3. 提交 = 一次 commit → Actions 构建 → 1–2 分钟上线
4. 插图走 `public/images/`，自动插入 `![]()` 片段

PAT 不落库、不上传，只在本浏览器。仓库里没有任何密钥。

## 七、留言

giscus，数据存 GitHub Discussions。代价：留言者需 GitHub 账号。这是纯静态托管唯一不引入外部服务的方案。

启用步骤：仓库 Settings → 开启 Discussions → giscus.app 生成 `repoId` / `categoryId` → 填入 `src/site.config.ts`。未填时页面显示接入提示，不会报错。

## 八、音乐

`public/audio/eikyuu-hours.mp3`，`<audio loop muted autoplay>` 入站即起播（静音），监听首个 `pointerdown / keydown / wheel / scroll` 后 900ms 淡入到 0.4 音量。

带声自动播放会被 Chrome、Safari、iOS 静默拦截，代码不报错、音量恒为 0。静音起播 + 手势解锁是唯一稳的实现。右下角三根竖条点击可静音/恢复。

## 九、构建与部署

```
npm run build      # 产物 dist/，18 页
.github/workflows/deploy.yml   # push main 自动发布到 Pages
```

仓库名须为 `Frostsnow35.github.io` 才能拿到根域名，否则站点落在 `/blog-v2/` 子路径，`astro.config.mjs` 需补 `base`。

## 十、已知取舍

| 项 | 取舍 |
|---|---|
| github.io 国内访问 | 可用，但部分运营商首包 1–3s，偶尔抖动。切换自有域名时改 `site` 一处即可 |
| 留言需 GitHub 登录 | 纯静态托管的硬约束 |
| 字体子集 | 新增生僻字需重跑 `build_font.py`，否则回退系统宋体 |
| 无评论 | 留言板替代，不再单独做文章评论 |
| 旧站数据 | Supabase 项目实例可保留只读，确认新站稳定后再停 |
