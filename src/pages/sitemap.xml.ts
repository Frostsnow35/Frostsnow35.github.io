import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export const GET: APIRoute = async ({ site }) => {
  const base = (site ?? new URL('https://frostsnow35.github.io')).href.replace(/\/$/, '');
  const posts = (await getCollection('posts')).sort(
    (a, b) => b.data.date.getTime() - a.data.date.getTime()
  );
  const now = new Date().toISOString();

  const entries: { loc: string; lastmod: string }[] = [
    { loc: `${base}/`, lastmod: now },
    { loc: `${base}/posts/`, lastmod: posts[0] ? posts[0].data.date.toISOString() : now },
    { loc: `${base}/about/`, lastmod: now },
    { loc: `${base}/guestbook/`, lastmod: now },
    ...posts.map((p) => ({
      loc: `${base}/posts/${p.id}/`,
      lastmod: p.data.date.toISOString(),
    })),
  ];

  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries
  .map(
    (e) => `  <url>
    <loc>${esc(e.loc)}</loc>
    <lastmod>${e.lastmod}</lastmod>
  </url>`
  )
  .join('\n')}
</urlset>
`;

  return new Response(body, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
