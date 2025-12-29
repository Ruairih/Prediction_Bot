/**
 * Sidebar Navigation Component
 *
 * Premium collapsible sidebar with navigation links and theme-aware styling.
 */
import { NavLink } from 'react-router-dom';
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
}

export function Sidebar({ collapsed = false, onToggle }: SidebarProps) {
  return (
    <aside
      data-testid="sidebar"
      data-collapsed={collapsed}
      className={clsx(
        'relative flex flex-col transition-all duration-300 ease-smooth',
        'bg-bg-secondary border-r border-border',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo/Brand Area */}
      <div className={clsx(
        'relative px-4 pt-6 pb-4 transition-all duration-300',
        collapsed ? 'items-center' : ''
      )}>
        {!collapsed && (
          <>
            <div className="text-[10px] uppercase tracking-[0.4em] text-text-muted font-medium">
              Polymarket
            </div>
            <div className="text-xl font-semibold text-text-primary mt-1 tracking-tight">
              Trade Desk
            </div>
            <div className="absolute bottom-0 left-4 right-4 h-px bg-gradient-to-r from-border via-accent-primary/30 to-border" />
          </>
        )}
        {collapsed && (
          <div className="flex justify-center">
            <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center text-white font-bold text-sm shadow-glow-primary">
              P
            </div>
          </div>
        )}
      </div>

      {/* Toggle button */}
      <button
        onClick={onToggle}
        className={clsx(
          'group h-10 flex items-center justify-center mx-2 rounded-lg',
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
                collapsed && 'justify-center px-0'
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

                {/* Label and description */}
                {!collapsed && (
                  <div className="flex-1 min-w-0">
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
                )}

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
        collapsed ? 'px-2' : ''
      )}>
        {!collapsed ? (
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-positive animate-pulse" />
            <span className="text-xs text-text-muted">
              v1.0.0 · Live
            </span>
          </div>
        ) : (
          <div className="flex justify-center">
            <div className="w-2 h-2 rounded-full bg-positive animate-pulse" />
          </div>
        )}
      </div>

      {/* Decorative gradient */}
      <div className="absolute inset-y-0 right-0 w-px bg-gradient-to-b from-transparent via-accent-primary/20 to-transparent pointer-events-none" />
    </aside>
  );
}
