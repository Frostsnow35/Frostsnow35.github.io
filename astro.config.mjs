import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://frostsnow35.github.io',
  build: {
    inlineStylesheets: 'auto',
  },
  markdown: {
    shikiConfig: {
      themes: { light: 'github-light', dark: 'github-dark' },
      defaultColor: false,
      wrap: false,
    },
  },
  compressHTML: true,
  devToolbar: { enabled: false },
});
