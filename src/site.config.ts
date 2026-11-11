export const site = {
  title: 'Frostsnow',
  tagline: 'Ce bas monde est le paradis unique.',
  description: '计算机专业学生的技术笔记与随笔。',
  author: 'Frostsnow',
  email: 'Silen_L@163.com',
  github: 'https://github.com/Frostsnow35',
  bilibili: 'https://space.bilibili.com/454395506',
  startYear: 2026,

  // 留言板：giscus（GitHub Discussions）
  giscus: {
    repo: 'Frostsnow35/Frostsnow35.github.io',
    repoId: 'R_kgDOVqSySA',
    category: 'Announcements',
    categoryId: 'DIC_kwDOVqSySM4DK3l_',
    mapping: 'pathname',
  },

  // 站点音乐：入站静音起播，首次交互后淡入到设定音量
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
