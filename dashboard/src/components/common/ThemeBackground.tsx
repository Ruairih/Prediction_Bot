/**
 * Theme Background Component
 *
 * Renders artistic decorative backgrounds that change with each theme.
 * Creates immersive visual experiences beyond simple color changes.
 */
import { useTheme } from '../../contexts/ThemeContext';

export function ThemeBackground() {
  const { themeName } = useTheme();

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden" style={{ zIndex: 0 }}>
      {/* Solid base color */}
      <div className="absolute inset-0 transition-colors duration-500"
           style={{ background: 'var(--bg-primary)' }} />

      {/* Gradient overlay layer */}
      <div className="absolute inset-0 transition-all duration-700 ease-out"
           style={{ background: 'var(--gradient-background)' }} />

      {/* Theme-specific artistic elements */}
      {themeName === 'midnight-pro' && <MidnightProBackground />}
      {themeName === 'aurora' && <AuroraBackground />}
      {themeName === 'cyber' && <CyberBackground />}
      {themeName === 'obsidian' && <ObsidianBackground />}
      {themeName === 'daylight' && <DaylightBackground />}

      {/* Subtle noise texture overlay */}
      <div
        className="absolute inset-0 opacity-[0.015]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        }}
      />
    </div>
  );
}

/**
 * Midnight Pro - Professional grid with subtle pulse
 */
function MidnightProBackground() {
  return (
    <>
      {/* Grid pattern */}
      <svg className="absolute inset-0 w-full h-full opacity-[0.06]">
        <defs>
          <pattern id="grid-midnight" width="60" height="60" patternUnits="userSpaceOnUse">
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#58a6ff" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid-midnight)" />
      </svg>

      {/* Floating orbs - more prominent */}
      <div className="absolute top-[5%] left-[10%] w-[500px] h-[500px] rounded-full opacity-40 animate-float-slow"
           style={{ background: 'radial-gradient(circle, rgba(88, 166, 255, 0.4) 0%, transparent 70%)', filter: 'blur(40px)' }} />
      <div className="absolute bottom-[15%] right-[5%] w-[400px] h-[400px] rounded-full opacity-30 animate-float-delayed"
           style={{ background: 'radial-gradient(circle, rgba(56, 139, 253, 0.35) 0%, transparent 70%)', filter: 'blur(50px)' }} />
      <div className="absolute top-[50%] left-[50%] w-[300px] h-[300px] rounded-full opacity-20 animate-float-particle"
           style={{ background: 'radial-gradient(circle, rgba(88, 166, 255, 0.3) 0%, transparent 70%)', filter: 'blur(30px)', transform: 'translate(-50%, -50%)' }} />
    </>
  );
}

/**
 * Aurora - Northern lights with animated waves
 */
function AuroraBackground() {
  // Generate stable star positions using a seeded approach
  const stars = Array.from({ length: 80 }).map((_, i) => ({
    cx: ((i * 31) % 100),
    cy: ((i * 47) % 100),
    r: ((i % 3) + 1) * 0.6,
    delay: (i % 10) * 0.3,
  }));

  return (
    <>
      {/* Aurora bands - more vivid */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="aurora-band aurora-band-1" style={{ opacity: 0.5 }} />
        <div className="aurora-band aurora-band-2" style={{ opacity: 0.4 }} />
        <div className="aurora-band aurora-band-3" style={{ opacity: 0.35 }} />
      </div>

      {/* Star field - more visible */}
      <svg className="absolute inset-0 w-full h-full opacity-60">
        <defs>
          <radialGradient id="star-glow">
            <stop offset="0%" stopColor="#fff" stopOpacity="1" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
        </defs>
        {stars.map((star, i) => (
          <circle
            key={i}
            cx={`${star.cx}%`}
            cy={`${star.cy}%`}
            r={star.r}
            fill="url(#star-glow)"
            className="animate-twinkle"
            style={{ animationDelay: `${star.delay}s` }}
          />
        ))}
      </svg>

      {/* Glowing aurora orbs - more dramatic */}
      <div className="absolute top-[-10%] left-[15%] w-[700px] h-[500px] opacity-50 animate-aurora"
           style={{ background: 'radial-gradient(ellipse at center, rgba(6, 182, 212, 0.5) 0%, transparent 70%)', filter: 'blur(60px)' }} />
      <div className="absolute top-[5%] right-[10%] w-[600px] h-[450px] opacity-45 animate-aurora-delayed"
           style={{ background: 'radial-gradient(ellipse at center, rgba(139, 92, 246, 0.45) 0%, transparent 70%)', filter: 'blur(50px)' }} />
      <div className="absolute bottom-[20%] left-[25%] w-[500px] h-[400px] opacity-35 animate-aurora-slow"
           style={{ background: 'radial-gradient(ellipse at center, rgba(236, 72, 153, 0.4) 0%, transparent 70%)', filter: 'blur(40px)' }} />
    </>
  );
}

/**
 * Cyber - Neon grid with scan lines and glitch effects
 */
function CyberBackground() {
  return (
    <>
      {/* Perspective grid - more visible */}
      <div className="absolute bottom-0 left-0 right-0 h-[70%] overflow-hidden opacity-50">
        <div className="cyber-grid" />
      </div>

      {/* Horizontal scan lines */}
      <div className="absolute inset-0 opacity-[0.05]"
           style={{
             backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 240, 255, 0.15) 2px, rgba(0, 240, 255, 0.15) 4px)',
           }} />

      {/* Neon glow orbs */}
      <div className="absolute top-[10%] left-[5%] w-[400px] h-[400px] rounded-full opacity-30"
           style={{ background: 'radial-gradient(circle, rgba(0, 240, 255, 0.4) 0%, transparent 70%)', filter: 'blur(60px)' }} />
      <div className="absolute bottom-[20%] right-[10%] w-[350px] h-[350px] rounded-full opacity-25"
           style={{ background: 'radial-gradient(circle, rgba(255, 0, 170, 0.35) 0%, transparent 70%)', filter: 'blur(50px)' }} />

      {/* Neon accent lines */}
      <svg className="absolute inset-0 w-full h-full">
        <defs>
          <linearGradient id="neon-cyan" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="transparent" />
            <stop offset="50%" stopColor="#00f0ff" />
            <stop offset="100%" stopColor="transparent" />
          </linearGradient>
          <linearGradient id="neon-pink" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="transparent" />
            <stop offset="50%" stopColor="#ff00aa" />
            <stop offset="100%" stopColor="transparent" />
          </linearGradient>
          <filter id="neon-glow">
            <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        {/* Animated lines - more visible */}
        <line x1="0" y1="15%" x2="100%" y2="15%" stroke="url(#neon-cyan)" strokeWidth="2"
              filter="url(#neon-glow)" opacity="0.6" className="animate-scan" />
        <line x1="0" y1="85%" x2="100%" y2="85%" stroke="url(#neon-pink)" strokeWidth="2"
              filter="url(#neon-glow)" opacity="0.5" className="animate-scan-delayed" />
      </svg>

      {/* Corner decorations - more prominent */}
      <div className="absolute top-6 left-6 w-32 h-32 border-l-2 border-t-2 border-[#00f0ff]/50" />
      <div className="absolute top-6 right-6 w-32 h-32 border-r-2 border-t-2 border-[#ff00aa]/50" />
      <div className="absolute bottom-6 left-6 w-32 h-32 border-l-2 border-b-2 border-[#ff00aa]/50" />
      <div className="absolute bottom-6 right-6 w-32 h-32 border-r-2 border-b-2 border-[#00f0ff]/50" />

      {/* Additional corner details */}
      <div className="absolute top-6 left-6 w-4 h-4 bg-[#00f0ff]/80" />
      <div className="absolute top-6 right-6 w-4 h-4 bg-[#ff00aa]/80" />
      <div className="absolute bottom-6 left-6 w-4 h-4 bg-[#ff00aa]/80" />
      <div className="absolute bottom-6 right-6 w-4 h-4 bg-[#00f0ff]/80" />
    </>
  );
}

/**
 * Obsidian - Elegant luxury with gold accents and subtle texture
 */
function ObsidianBackground() {
  // Generate stable particle positions
  const particles = Array.from({ length: 30 }).map((_, i) => ({
    left: ((i * 37) % 100),
    top: ((i * 53) % 100),
    delay: (i % 10),
    duration: 15 + (i % 5) * 2,
  }));

  return (
    <>
      {/* Elegant diagonal lines - more visible */}
      <svg className="absolute inset-0 w-full h-full opacity-[0.04]">
        <defs>
          <pattern id="diagonal-obsidian" width="40" height="40" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="40" stroke="#d4a574" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#diagonal-obsidian)" />
      </svg>

      {/* Gold accent gradients - more dramatic */}
      <div className="absolute top-0 right-0 w-2/3 h-2/3 opacity-25"
           style={{ background: 'radial-gradient(ellipse at 100% 0%, rgba(212, 165, 116, 0.4) 0%, transparent 60%)', filter: 'blur(40px)' }} />
      <div className="absolute bottom-0 left-0 w-1/2 h-1/2 opacity-20"
           style={{ background: 'radial-gradient(ellipse at 0% 100%, rgba(184, 149, 110, 0.35) 0%, transparent 60%)', filter: 'blur(30px)' }} />

      {/* Central gold highlight */}
      <div className="absolute top-1/3 left-1/2 w-[400px] h-[400px] opacity-15 -translate-x-1/2"
           style={{ background: 'radial-gradient(circle, rgba(212, 165, 116, 0.3) 0%, transparent 70%)', filter: 'blur(50px)' }} />

      {/* Vignette effect */}
      <div className="absolute inset-0"
           style={{ background: 'radial-gradient(ellipse at center, transparent 0%, rgba(0, 0, 0, 0.5) 100%)' }} />

      {/* Gold particles - more visible */}
      {particles.map((p, i) => (
        <div
          key={i}
          className="absolute w-1 h-1 rounded-full bg-[#d4a574]/40 animate-float-particle"
          style={{
            left: `${p.left}%`,
            top: `${p.top}%`,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        />
      ))}
    </>
  );
}

/**
 * Daylight - Clean, warm with subtle nature-inspired patterns
 */
function DaylightBackground() {
  return (
    <>
      {/* Soft gradient overlays - more visible warm tones */}
      <div className="absolute top-0 left-0 w-full h-2/3 opacity-70"
           style={{ background: 'linear-gradient(180deg, rgba(15, 107, 110, 0.06) 0%, transparent 100%)' }} />
      <div className="absolute bottom-0 right-0 w-3/4 h-1/2 opacity-60"
           style={{ background: 'radial-gradient(ellipse at 100% 100%, rgba(177, 58, 45, 0.08) 0%, transparent 70%)' }} />
      <div className="absolute top-0 right-0 w-1/2 h-1/2 opacity-50"
           style={{ background: 'radial-gradient(ellipse at 100% 0%, rgba(194, 147, 43, 0.06) 0%, transparent 60%)' }} />

      {/* Subtle topographic lines - more visible */}
      <svg className="absolute inset-0 w-full h-full opacity-[0.04]">
        <defs>
          <pattern id="topo-daylight" width="120" height="120" patternUnits="userSpaceOnUse">
            <circle cx="60" cy="60" r="20" fill="none" stroke="#0f6b6e" strokeWidth="0.5" />
            <circle cx="60" cy="60" r="40" fill="none" stroke="#0f6b6e" strokeWidth="0.5" />
            <circle cx="60" cy="60" r="60" fill="none" stroke="#0f6b6e" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#topo-daylight)" />
      </svg>

      {/* Warm bokeh effects - larger and more visible */}
      <div className="absolute top-[15%] left-[5%] w-[300px] h-[300px] rounded-full opacity-40 animate-float-slow"
           style={{ background: 'radial-gradient(circle, rgba(15, 107, 110, 0.25) 0%, transparent 70%)', filter: 'blur(50px)' }} />
      <div className="absolute top-[30%] right-[15%] w-[250px] h-[250px] rounded-full opacity-35 animate-float-delayed"
           style={{ background: 'radial-gradient(circle, rgba(177, 58, 45, 0.2) 0%, transparent 70%)', filter: 'blur(40px)' }} />
      <div className="absolute bottom-[25%] left-[25%] w-[200px] h-[200px] rounded-full opacity-30 animate-float-particle"
           style={{ background: 'radial-gradient(circle, rgba(194, 147, 43, 0.25) 0%, transparent 70%)', filter: 'blur(35px)' }} />
      <div className="absolute bottom-[10%] right-[30%] w-[180px] h-[180px] rounded-full opacity-25 animate-float-slow"
           style={{ background: 'radial-gradient(circle, rgba(15, 107, 110, 0.2) 0%, transparent 70%)', filter: 'blur(30px)' }} />

      {/* Light rays effect */}
      <div className="absolute top-0 left-1/3 w-32 h-screen opacity-[0.03]"
           style={{ background: 'linear-gradient(180deg, rgba(255, 255, 255, 1) 0%, transparent 50%)' }} />
      <div className="absolute top-0 right-1/4 w-24 h-screen opacity-[0.025]"
           style={{ background: 'linear-gradient(180deg, rgba(255, 255, 255, 1) 0%, transparent 40%)' }} />
    </>
  );
}
