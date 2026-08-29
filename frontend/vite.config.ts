import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    strictPort: false,
    // 允许 NODE_MODULES junction(原 frontend/node_modules 与 platform 跨目录) 被 vite 访问, 修复字体 403
    fs: {
      allow: ['D:/paper/cc/projects/multi_agent_platform_langgraph/frontend/node_modules', '.'],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        secure: false,
      },
    },
  },
  // vite preview 模式(serve dist/)同样把 /api 代理到后端, 让 build 后可单端口访问
  preview: {
    port: 5173,
    host: '0.0.0.0',
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        secure: false,
      },
    },
  },
});
