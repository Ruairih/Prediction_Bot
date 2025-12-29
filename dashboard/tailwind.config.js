/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dynamic theme colors via CSS custom properties
        'bg-primary': 'var(--bg-primary)',
        'bg-secondary': 'var(--bg-secondary)',
        'bg-tertiary': 'var(--bg-tertiary)',
        'bg-glass': 'var(--bg-glass)',
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted': 'var(--text-muted)',
        'border': 'var(--border)',
        'border-subtle': 'var(--border-subtle)',
        'accent-primary': 'var(--accent-primary)',
        'accent-secondary': 'var(--accent-secondary)',
        'positive': 'var(--positive)',
        'negative': 'var(--negative)',
        'warning': 'var(--warning)',
        'info': 'var(--info)',
        // Legacy color aliases for compatibility
        'accent-blue': 'var(--accent-primary)',
        'accent-green': 'var(--positive)',
        'accent-red': 'var(--negative)',
        'accent-yellow': 'var(--warning)',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        'kpi': ['1.75rem', { lineHeight: '1.2', fontWeight: '600', letterSpacing: '-0.02em' }],
        'label': ['0.65rem', { lineHeight: '1.4', fontWeight: '500', letterSpacing: '0.15em' }],
      },
      borderRadius: {
        'card': 'var(--border-radius)',
        'lg': '12px',
        'xl': '16px',
        '2xl': '20px',
      },
      boxShadow: {
        'card': 'var(--card-shadow)',
        'glow-primary': '0 0 20px var(--glow-primary)',
        'glow-positive': '0 0 20px var(--glow-positive)',
        'glow-negative': '0 0 20px var(--glow-negative)',
        'subtle': '0 1px 2px rgba(0, 0, 0, 0.1)',
        'elevated': '0 4px 24px rgba(0, 0, 0, 0.2)',
      },
      backgroundImage: {
        'gradient-primary': 'var(--gradient-primary)',
        'gradient-accent': 'var(--gradient-accent)',
        'gradient-bg': 'var(--gradient-background)',
      },
      backdropBlur: {
        'glass': '12px',
        'strong': '20px',
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease forwards',
        'slide-in': 'slide-in-left 0.3s ease forwards',
        'scale-in': 'scale-in 0.2s ease forwards',
        'pulse-glow': 'pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer': 'shimmer 1.5s infinite',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-left': {
          from: { opacity: '0', transform: 'translateX(-16px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.95)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 0 0 var(--glow-primary)' },
          '50%': { opacity: '0.8', boxShadow: '0 0 20px 10px transparent' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      transitionDuration: {
        '250': '250ms',
      },
      transitionTimingFunction: {
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
}
