/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
      colors: {
        bg:        'var(--bg)',
        surface:   'var(--surface)',
        surface2:  'var(--surface-2)',
        surface3:  'var(--surface-3)',
        accent:    { DEFAULT: 'var(--accent)', 2: 'var(--accent-2)' },
        text1:     'var(--text-1)',
        text2:     'var(--text-2)',
        text3:     'var(--text-3)',
        text4:     'var(--text-4)',
        green:     'var(--green)',
        amber:     { DEFAULT: 'var(--amber)', warn: 'var(--amber)' },
        red:       'var(--red)',
      },
      borderColor: {
        DEFAULT: 'var(--border)',
        strong: 'var(--border-strong)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
    },
  },
  plugins: [],
};
