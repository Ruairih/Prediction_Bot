/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Warm, daylight trading theme
        'bg-primary': '#f5f1ea',
        'bg-secondary': '#ffffff',
        'bg-tertiary': '#efe7db',
        'border': '#e5dccf',
        'text-primary': '#1b1b1b',
        'text-secondary': '#5b5b5b',
        'accent-blue': '#0f6b6e',
        'accent-green': '#1e7a5a',
        'accent-red': '#b13a2d',
        'accent-yellow': '#c2932b',
        'accent-purple': '#5e596d',
      },
    },
  },
  plugins: [],
}
