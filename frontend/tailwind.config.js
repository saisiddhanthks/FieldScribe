/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        void: '#000000', panel: '#06080a', raise: '#0c1013', line: '#182027', line2: '#242e36',
        ink: '#e4ebee', dim: '#8a979f', faint: '#55626b',
        hr: '#3ee07f', spo2: '#35d0f0', bp: '#f2f4f5', resp: '#f3cf3a', alarm: '#ff4b4b', warn: '#ffa733', co2: '#c08bff',
      },
      fontFamily: {
        sans: ['Barlow', 'system-ui', 'sans-serif'],
        num: ['"Barlow Condensed"', 'Barlow', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
