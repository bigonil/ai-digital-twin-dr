/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'dt-bg':      '#0a0e1a',
        'dt-surface': '#111827',
        'dt-border':  '#1f2937',
        'dt-accent':  '#3b82f6',
        'dt-danger':  '#ef4444',
        'dt-warning': '#f59e0b',
        'dt-success': '#10b981',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
