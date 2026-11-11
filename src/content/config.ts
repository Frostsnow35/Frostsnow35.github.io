import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    category: z.string().default('随笔'),
    tags: z.array(z.string()).default([]),
    excerpt: z.string().default(''),
    readTime: z.number().default(5),
    legacyId: z.number().optional(),
  }),
});

export const collections = { posts };
