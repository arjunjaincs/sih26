/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'pramaan-navy': '#0B1F3A',
        'pramaan-navy-header': '#1F497D',
        'pramaan-steelblue': '#4F81BD',
        'pramaan-gold': '#C9A24B',
        'pramaan-red': '#B03A2E',
        'pramaan-green': '#3F7D4F',
        'pramaan-text-dark': '#F4F6F9',
        'pramaan-text-light': '#3B3F45',
      },
      fontFamily: {
        'sans': ['system-ui', 'sans-serif'],
        'header': ['Inter', 'Space Grotesk', 'sans-serif'],
        'serif': ['Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif'],
        'doc': ['Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif'],
        'mono': ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', '"Liberation Mono"', 'monospace'],
      }
    },
  },
  plugins: [],
}
