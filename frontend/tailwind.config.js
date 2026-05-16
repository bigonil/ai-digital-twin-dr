/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'dt-bg':      'var(--dt-bg)',
        'dt-surface': 'var(--dt-surface)',
        'dt-border':  'var(--dt-border)',
        'dt-accent':  'var(--dt-accent)',
        'dt-danger':  'var(--dt-danger)',
        'dt-warning': 'var(--dt-warning)',
        'dt-success': 'var(--dt-success)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
