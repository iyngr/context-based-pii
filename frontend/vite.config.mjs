import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react({
        jsx: 'react-jsx',
        include: '**/*.{js,jsx}'
    })],
    server: {
        port: 3000,
    },
    build: {
        outDir: 'build'
    }
})