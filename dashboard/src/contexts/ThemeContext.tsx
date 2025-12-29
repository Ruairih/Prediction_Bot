/**
 * Theme Context
 *
 * Provides theme management with multiple artistic themes.
 * Persists selection to localStorage.
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type ThemeName =
  | 'midnight-pro'      // Dark professional (Bloomberg-inspired)
  | 'aurora'            // Midnight with aurora gradients
  | 'cyber'             // Neon cyberpunk
  | 'obsidian'          // Deep black with gold accents
  | 'daylight';         // Light warm theme (current)

export interface ThemeColors {
  // Base surfaces
  bgPrimary: string;
  bgSecondary: string;
  bgTertiary: string;
  bgGlass: string;

  // Text
  textPrimary: string;
  textSecondary: string;
  textMuted: string;

  // Borders & lines
  border: string;
  borderSubtle: string;

  // Semantic colors
  accentPrimary: string;
  accentSecondary: string;
  positive: string;
  negative: string;
  warning: string;
  info: string;

  // Special effects
  glowPrimary: string;
  glowPositive: string;
  glowNegative: string;

  // Gradients (CSS values)
  gradientPrimary: string;
  gradientAccent: string;
  gradientBackground: string;
}

export interface Theme {
  name: ThemeName;
  label: string;
  description: string;
  colors: ThemeColors;
  isDark: boolean;
  effects: {
    glassBlur: string;
    cardShadow: string;
    glowIntensity: 'none' | 'subtle' | 'medium' | 'intense';
    borderRadius: string;
  };
}

// ============================================================================
// Theme Definitions
// ============================================================================

export const themes: Record<ThemeName, Theme> = {
  'midnight-pro': {
    name: 'midnight-pro',
    label: 'Midnight Pro',
    description: 'Professional dark theme inspired by Bloomberg Terminal',
    isDark: true,
    colors: {
      bgPrimary: '#0a0c10',
      bgSecondary: '#12151c',
      bgTertiary: '#1a1e28',
      bgGlass: 'rgba(18, 21, 28, 0.85)',
      textPrimary: '#e6edf3',
      textSecondary: '#8b949e',
      textMuted: '#484f58',
      border: '#21262d',
      borderSubtle: '#161b22',
      accentPrimary: '#58a6ff',
      accentSecondary: '#388bfd',
      positive: '#3fb950',
      negative: '#f85149',
      warning: '#d29922',
      info: '#58a6ff',
      glowPrimary: 'rgba(88, 166, 255, 0.15)',
      glowPositive: 'rgba(63, 185, 80, 0.15)',
      glowNegative: 'rgba(248, 81, 73, 0.15)',
      gradientPrimary: 'linear-gradient(135deg, #58a6ff 0%, #388bfd 100%)',
      gradientAccent: 'linear-gradient(180deg, rgba(88, 166, 255, 0.1) 0%, transparent 100%)',
      gradientBackground: 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(88, 166, 255, 0.08), transparent)',
    },
    effects: {
      glassBlur: 'blur(12px)',
      cardShadow: '0 1px 3px rgba(0,0,0,0.3), 0 4px 12px rgba(0,0,0,0.2)',
      glowIntensity: 'subtle',
      borderRadius: '12px',
    },
  },

  'aurora': {
    name: 'aurora',
    label: 'Aurora',
    description: 'Ethereal dark theme with northern lights gradients',
    isDark: true,
    colors: {
      bgPrimary: '#0b0d14',
      bgSecondary: '#111827',
      bgTertiary: '#1f2937',
      bgGlass: 'rgba(17, 24, 39, 0.75)',
      textPrimary: '#f3f4f6',
      textSecondary: '#9ca3af',
      textMuted: '#4b5563',
      border: '#374151',
      borderSubtle: '#1f2937',
      accentPrimary: '#06b6d4',
      accentSecondary: '#8b5cf6',
      positive: '#10b981',
      negative: '#ef4444',
      warning: '#f59e0b',
      info: '#06b6d4',
      glowPrimary: 'rgba(6, 182, 212, 0.2)',
      glowPositive: 'rgba(16, 185, 129, 0.2)',
      glowNegative: 'rgba(239, 68, 68, 0.2)',
      gradientPrimary: 'linear-gradient(135deg, #06b6d4 0%, #8b5cf6 50%, #ec4899 100%)',
      gradientAccent: 'linear-gradient(180deg, rgba(139, 92, 246, 0.15) 0%, rgba(6, 182, 212, 0.05) 100%)',
      gradientBackground: `
        radial-gradient(ellipse 100% 80% at 20% -30%, rgba(6, 182, 212, 0.15), transparent 50%),
        radial-gradient(ellipse 80% 60% at 80% -10%, rgba(139, 92, 246, 0.12), transparent 50%),
        radial-gradient(ellipse 60% 40% at 50% 100%, rgba(236, 72, 153, 0.08), transparent)
      `,
    },
    effects: {
      glassBlur: 'blur(16px)',
      cardShadow: '0 4px 24px rgba(0,0,0,0.3), 0 0 1px rgba(255,255,255,0.1)',
      glowIntensity: 'medium',
      borderRadius: '16px',
    },
  },

  'cyber': {
    name: 'cyber',
    label: 'Cyber',
    description: 'Futuristic neon cyberpunk aesthetic',
    isDark: true,
    colors: {
      bgPrimary: '#0a0a0f',
      bgSecondary: '#0f0f18',
      bgTertiary: '#161625',
      bgGlass: 'rgba(15, 15, 24, 0.8)',
      textPrimary: '#ffffff',
      textSecondary: '#a0a0b0',
      textMuted: '#505060',
      border: '#2a2a3e',
      borderSubtle: '#1a1a2e',
      accentPrimary: '#00f0ff',
      accentSecondary: '#ff00aa',
      positive: '#00ff88',
      negative: '#ff3366',
      warning: '#ffaa00',
      info: '#00f0ff',
      glowPrimary: 'rgba(0, 240, 255, 0.25)',
      glowPositive: 'rgba(0, 255, 136, 0.25)',
      glowNegative: 'rgba(255, 51, 102, 0.25)',
      gradientPrimary: 'linear-gradient(135deg, #00f0ff 0%, #ff00aa 100%)',
      gradientAccent: 'linear-gradient(180deg, rgba(0, 240, 255, 0.2) 0%, rgba(255, 0, 170, 0.1) 100%)',
      gradientBackground: `
        radial-gradient(ellipse 60% 40% at 10% 0%, rgba(0, 240, 255, 0.12), transparent),
        radial-gradient(ellipse 50% 30% at 90% 10%, rgba(255, 0, 170, 0.1), transparent),
        linear-gradient(180deg, #0a0a0f 0%, #0f0f18 100%)
      `,
    },
    effects: {
      glassBlur: 'blur(20px)',
      cardShadow: '0 0 1px rgba(0, 240, 255, 0.5), 0 4px 24px rgba(0,0,0,0.4)',
      glowIntensity: 'intense',
      borderRadius: '8px',
    },
  },

  'obsidian': {
    name: 'obsidian',
    label: 'Obsidian',
    description: 'Deep black with refined gold accents',
    isDark: true,
    colors: {
      bgPrimary: '#000000',
      bgSecondary: '#0a0a0a',
      bgTertiary: '#141414',
      bgGlass: 'rgba(10, 10, 10, 0.9)',
      textPrimary: '#fafafa',
      textSecondary: '#a3a3a3',
      textMuted: '#525252',
      border: '#262626',
      borderSubtle: '#171717',
      accentPrimary: '#d4a574',
      accentSecondary: '#b8956e',
      positive: '#22c55e',
      negative: '#ef4444',
      warning: '#f59e0b',
      info: '#d4a574',
      glowPrimary: 'rgba(212, 165, 116, 0.15)',
      glowPositive: 'rgba(34, 197, 94, 0.15)',
      glowNegative: 'rgba(239, 68, 68, 0.15)',
      gradientPrimary: 'linear-gradient(135deg, #d4a574 0%, #b8956e 100%)',
      gradientAccent: 'linear-gradient(180deg, rgba(212, 165, 116, 0.1) 0%, transparent 100%)',
      gradientBackground: 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(212, 165, 116, 0.05), transparent)',
    },
    effects: {
      glassBlur: 'blur(12px)',
      cardShadow: '0 2px 8px rgba(0,0,0,0.5), 0 0 1px rgba(212, 165, 116, 0.1)',
      glowIntensity: 'subtle',
      borderRadius: '10px',
    },
  },

  'daylight': {
    name: 'daylight',
    label: 'Daylight',
    description: 'Clean warm light theme',
    isDark: false,
    colors: {
      bgPrimary: '#f8f6f2',
      bgSecondary: '#ffffff',
      bgTertiary: '#f0ebe3',
      bgGlass: 'rgba(255, 255, 255, 0.85)',
      textPrimary: '#1a1a1a',
      textSecondary: '#5c5c5c',
      textMuted: '#9a9a9a',
      border: '#e5dfd5',
      borderSubtle: '#f0ebe3',
      accentPrimary: '#0f6b6e',
      accentSecondary: '#0a5456',
      positive: '#1e7a5a',
      negative: '#b13a2d',
      warning: '#c2932b',
      info: '#0f6b6e',
      glowPrimary: 'rgba(15, 107, 110, 0.1)',
      glowPositive: 'rgba(30, 122, 90, 0.1)',
      glowNegative: 'rgba(177, 58, 45, 0.1)',
      gradientPrimary: 'linear-gradient(135deg, #0f6b6e 0%, #0a5456 100%)',
      gradientAccent: 'linear-gradient(180deg, rgba(15, 107, 110, 0.08) 0%, transparent 100%)',
      gradientBackground: `
        radial-gradient(ellipse 100% 50% at 10% -10%, rgba(15, 107, 110, 0.08), transparent 60%),
        radial-gradient(ellipse 80% 40% at 90% 0%, rgba(177, 58, 45, 0.06), transparent 55%),
        linear-gradient(180deg, #f8f6f2 0%, #f3ede3 100%)
      `,
    },
    effects: {
      glassBlur: 'blur(10px)',
      cardShadow: '0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04)',
      glowIntensity: 'none',
      borderRadius: '16px',
    },
  },
};

// ============================================================================
// Context
// ============================================================================

interface ThemeContextValue {
  theme: Theme;
  themeName: ThemeName;
  setTheme: (name: ThemeName) => void;
  themes: typeof themes;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const STORAGE_KEY = 'polymarket-dashboard-theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeName, setThemeName] = useState<ThemeName>(() => {
    if (typeof window === 'undefined') return 'midnight-pro';
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && stored in themes) return stored as ThemeName;
    return 'midnight-pro';
  });

  const theme = themes[themeName];

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, themeName);

    // Apply CSS custom properties
    const root = document.documentElement;
    const { colors, effects, isDark } = theme;

    // Colors
    root.style.setProperty('--bg-primary', colors.bgPrimary);
    root.style.setProperty('--bg-secondary', colors.bgSecondary);
    root.style.setProperty('--bg-tertiary', colors.bgTertiary);
    root.style.setProperty('--bg-glass', colors.bgGlass);
    root.style.setProperty('--text-primary', colors.textPrimary);
    root.style.setProperty('--text-secondary', colors.textSecondary);
    root.style.setProperty('--text-muted', colors.textMuted);
    root.style.setProperty('--border', colors.border);
    root.style.setProperty('--border-subtle', colors.borderSubtle);
    root.style.setProperty('--accent-primary', colors.accentPrimary);
    root.style.setProperty('--accent-secondary', colors.accentSecondary);
    root.style.setProperty('--positive', colors.positive);
    root.style.setProperty('--negative', colors.negative);
    root.style.setProperty('--warning', colors.warning);
    root.style.setProperty('--info', colors.info);
    root.style.setProperty('--glow-primary', colors.glowPrimary);
    root.style.setProperty('--glow-positive', colors.glowPositive);
    root.style.setProperty('--glow-negative', colors.glowNegative);
    root.style.setProperty('--gradient-primary', colors.gradientPrimary);
    root.style.setProperty('--gradient-accent', colors.gradientAccent);
    root.style.setProperty('--gradient-background', colors.gradientBackground);

    // Effects
    root.style.setProperty('--glass-blur', effects.glassBlur);
    root.style.setProperty('--card-shadow', effects.cardShadow);
    root.style.setProperty('--border-radius', effects.borderRadius);

    // Dark/light mode class
    if (isDark) {
      document.body.classList.add('dark');
      document.body.classList.remove('light');
    } else {
      document.body.classList.add('light');
      document.body.classList.remove('dark');
    }
  }, [theme, themeName]);

  const setTheme = (name: ThemeName) => {
    setThemeName(name);
  };

  return (
    <ThemeContext.Provider value={{ theme, themeName, setTheme, themes }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
