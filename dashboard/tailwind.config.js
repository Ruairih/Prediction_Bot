/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark trading theme
        'bg-primary': '#0d1117',
        'bg-secondary': '#161b22',
        'bg-tertiary': '#21262d',
        'border': '#30363d',
        'text-primary': '#e6edf3',
        'text-secondary': '#8b949e',
        'accent-blue': '#58a6ff',
        'accent-green': '#3fb950',
        'accent-red': '#f85149',
        'accent-yellow': '#d29922',
        'accent-purple': '#a371f7',
      },
    },
  },
  plugins: [],
}
