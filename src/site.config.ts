export const site = {
  title: '霜雪旧曾谙',
  eyebrow: 'A MINIMALIST JOURNAL',
  tagline: '把想留住的东西写下来',
  description: '计算机专业学生的技术笔记与随笔。',
  author: '霜雪旧曾谙',
  email: 'Silen_L@163.com',
  github: 'https://github.com/Frostsnow35',
  startYear: 2025,

  // 留言板：giscus（GitHub Discussions）
  giscus: {
    repo: 'Frostsnow35/Frostsnow35.github.io',
    repoId: 'R_kgDOVqSySA',
    category: 'Announcements',
    categoryId: 'DIC_kwDOVqSySM4DK3l_',
    mapping: 'pathname',
  },

  // 站点音乐：入站静音起播，首次交互后淡入
  music: {
    src: '/audio/eikyuu-hours.mp3',
    title: 'eikyuu hours',
    volume: 0.4,
  },

  // 后台：纯前端直连 GitHub API，PAT 只存本机 localStorage
  admin: {
    owner: 'Frostsnow35',
    repo: 'Frostsnow35.github.io',
    branch: 'main',
    postsDir: 'src/content/posts',
    imagesDir: 'public/images',
  },
} as const;

export const nav = [
  { href: '/', label: '首页' },
  { href: '/posts/', label: '文章' },
  { href: '/about/', label: '关于' },
  { href: '/guestbook/', label: '留言' },
];
