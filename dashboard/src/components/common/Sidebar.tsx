/**
 * Sidebar Navigation Component
 *
 * Premium collapsible sidebar with navigation links and theme-aware styling.
 * Fully responsive with mobile overlay and hamburger toggle.
 */
import { useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import clsx from 'clsx';

const navItems = [
  { path: '/', label: 'Mission', icon: '⬢', description: 'Command center' },
  { path: '/positions', label: 'Portfolio', icon: '◈', description: 'Open positions' },
  { path: '/markets', label: 'Markets', icon: '▣', description: 'Market explorer' },
  { path: '/pipeline', label: 'Pipeline', icon: '⧗', description: 'Signal funnel' },
  { path: '/strategy', label: 'Strategy', icon: '◎', description: 'Trading rules' },
  { path: '/performance', label: 'Performance', icon: '▲', description: 'P&L analytics' },
  { path: '/risk', label: 'Risk', icon: '△', description: 'Exposure limits' },
  { path: '/activity', label: 'Activity', icon: '≋', description: 'Event stream' },
  { path: '/system', label: 'System', icon: '⧉', description: 'Health status' },
  { path: '/settings', label: 'Settings', icon: '⚙', description: 'Preferences' },
];

export interface SidebarProps {
  collapsed?: boolean;
  onToggle?: () => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export function Sidebar({ collapsed = false, onToggle, mobileOpen = false, onMobileClose }: SidebarProps) {
  const location = useLocation();

  // Close mobile sidebar on route change
  useEffect(() => {
    if (mobileOpen && onMobileClose) {
      onMobileClose();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // Close mobile sidebar on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileOpen && onMobileClose) {
        onMobileClose();
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [mobileOpen, onMobileClose]);

  // Prevent body scroll when mobile sidebar is open
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileOpen]);

  return (
    <>
      {/* Mobile overlay backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={onMobileClose}
          aria-hidden="true"
        />
      )}

      <aside
        data-testid="sidebar"
        data-collapsed={collapsed}
        className={clsx(
          'flex flex-col transition-all duration-300 ease-smooth',
          'bg-bg-secondary border-r border-border',
          // Desktop: relative positioning, width based on collapsed state
          'md:relative md:translate-x-0',
          collapsed ? 'md:w-16' : 'md:w-64',
          // Mobile: fixed positioning, full height, slide in/out
          'fixed inset-y-0 left-0 z-50 w-64',
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        )}
      >
        {/* Logo/Brand Area */}
        <div className={clsx(
          'relative px-4 pt-6 pb-4 transition-all duration-300',
          collapsed ? 'md:items-center' : ''
        )}>
          {/* Mobile: always show full branding */}
          <div className={clsx(collapsed ? 'hidden md:hidden' : 'block', 'md:block', collapsed && 'md:!hidden')}>
            <div className="text-[10px] uppercase tracking-[0.4em] text-text-muted font-medium">
              Polymarket
            </div>
            <div className="text-xl font-semibold text-text-primary mt-1 tracking-tight">
              Trade Desk
            </div>
            <div className="absolute bottom-0 left-4 right-4 h-px bg-gradient-to-r from-border via-accent-primary/30 to-border" />
          </div>
          {/* Collapsed icon - only on desktop when collapsed */}
          <div className={clsx(collapsed ? 'hidden md:flex justify-center' : 'hidden')}>
            <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center text-white font-bold text-sm shadow-glow-primary">
              P
            </div>
          </div>
        </div>

        {/* Toggle button - hidden on mobile, visible on desktop */}
        <button
          onClick={onToggle}
          className={clsx(
            'hidden md:flex',
            'group h-10 items-center justify-center mx-2 rounded-lg',
            'text-text-muted hover:text-text-primary hover:bg-bg-tertiary',
            'transition-all duration-200',
            'focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-inset'
          )}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <span className={clsx(
            'transition-transform duration-200',
            collapsed ? 'rotate-180' : ''
          )}>
            ←
          </span>
        </button>

        {/* Mobile close button */}
        <button
          onClick={onMobileClose}
          className={clsx(
            'md:hidden',
            'group h-10 flex items-center justify-center mx-2 rounded-lg',
            'text-text-muted hover:text-text-primary hover:bg-bg-tertiary',
            'transition-all duration-200',
            'focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-inset'
          )}
          aria-label="Close navigation menu"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              aria-label={collapsed ? item.label : undefined}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                clsx(
                  'group relative flex items-center gap-3 px-3 py-2.5 rounded-lg',
                  'transition-all duration-200',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary',
                  isActive ? [
                    'bg-accent-primary/10 text-accent-primary',
                  ] : [
                    'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
                  ],
                  // On mobile, always show full width; on desktop, collapse based on prop
                  collapsed && 'md:justify-center md:px-0'
                )
              }
            >
              {({ isActive }) => (
                <>
                  {/* Active indicator bar */}
                  {isActive && (
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-accent-primary rounded-r-full" />
                  )}

                  {/* Icon */}
                  <span className={clsx(
                    'text-lg transition-transform duration-200',
                    'group-hover:scale-110',
                    isActive && 'text-glow-primary'
                  )}>
                    {item.icon}
                  </span>

                  {/* Label and description - always show on mobile, conditional on desktop */}
                  <div className={clsx(
                    'flex-1 min-w-0',
                    collapsed && 'md:hidden'
                  )}>
                    <div className="text-sm font-medium truncate">
                      {item.label}
                    </div>
                    <div className={clsx(
                      'text-[10px] truncate transition-colors',
                      isActive ? 'text-accent-primary/70' : 'text-text-muted'
                    )}>
                      {item.description}
                    </div>
                  </div>

                  {/* Hover glow effect */}
                  <div className={clsx(
                    'absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none',
                    'bg-gradient-to-r from-accent-primary/5 to-transparent'
                  )} />
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className={clsx(
          'p-4 border-t border-border transition-all duration-300',
          collapsed ? 'md:px-2' : ''
        )}>
          {/* Full footer - show on mobile always, on desktop when not collapsed */}
          <div className={clsx(
            'flex items-center gap-2',
            collapsed && 'md:hidden'
          )}>
            <div
              className="w-2 h-2 rounded-full bg-positive animate-pulse"
              aria-hidden="true"
            />
            <span className="text-xs text-text-muted">
              v1.0.0 · Live
            </span>
            <span className="sr-only">System status: online and running</span>
          </div>
          {/* Collapsed footer - only on desktop when collapsed */}
          <div className={clsx(
            'justify-center',
            collapsed ? 'hidden md:flex' : 'hidden'
          )} aria-label="System status: online">
            <div
              className="w-2 h-2 rounded-full bg-positive animate-pulse"
              aria-hidden="true"
            />
            <span className="sr-only">System status: online and running</span>
          </div>
        </div>

        {/* Decorative gradient */}
        <div className="absolute inset-y-0 right-0 w-px bg-gradient-to-b from-transparent via-accent-primary/20 to-transparent pointer-events-none" />
      </aside>
    </>
  );
}
