/**
 * @Author: Mukhil Sundararaj
 * @Date:   2025-09-13 13:06:32
 * @Last Modified by:   Mukhil Sundararaj
 * @Last Modified time: 2025-09-13 13:17:34
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        medical: {
          primary: '#2563eb',
          secondary: '#1e40af',
          accent: '#3b82f6',
          success: '#10b981',
          warning: '#f59e0b',
          danger: '#ef4444',
          info: '#06b6d4',
          light: '#f8fafc',
          dark: '#1e293b'
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace']
      }
    },
  },
  plugins: [],
}
