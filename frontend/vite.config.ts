import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // D2 (2026-09-18): фронтенд-тесты — раньше их было 0, только backend.
  // `vitest` переиспользует этот же конфиг (алиасы, плагин React), а не
  // требует отдельного jest/babel-конвейера — минимальная надстройка.
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.ts",
    globals: true,
  },
  server: {
    host: true,
    port: 5173,
    watch: {
      // Bind-mount с хоста Windows в Linux-контейнер не всегда пробрасывает
      // нативные fs-события (inotify) — без polling Vite может не увидеть
      // изменения файла и отдавать устаревшую версию из памяти неограниченно
      // долго, до перезапуска контейнера. Обнаружено на практике 2026-09-12.
      usePolling: true,
      interval: 300,
    },
  },
});
