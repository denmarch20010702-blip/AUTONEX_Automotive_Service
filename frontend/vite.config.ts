import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
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
