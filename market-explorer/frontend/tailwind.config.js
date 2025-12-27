/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'pm-green': '#00d395',
        'pm-red': '#ff6b6b',
        'pm-blue': '#4dabf7',
      },
    },
  },
  plugins: [],
}
