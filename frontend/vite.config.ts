import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: env.VITE_API_BASE_URL
        ? undefined
        : {
            '/api': {
              target: 'http://127.0.0.1:9527',
              changeOrigin: true,
            },
          },
    },
  }
})
