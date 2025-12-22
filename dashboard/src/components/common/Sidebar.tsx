/**
 * Sidebar Navigation Component
 *
 * Collapsible sidebar with navigation links.
 */
import { NavLink } from 'react-router-dom';
import clsx from 'clsx';

const navItems = [
  { path: '/', label: 'Overview', icon: '🏠' },
  { path: '/positions', label: 'Positions', icon: '📊' },
  { path: '/strategy', label: 'Strategy', icon: '🎯' },
  { path: '/performance', label: 'Performance', icon: '📈' },
  { path: '/risk', label: 'Risk', icon: '⚠️' },
  { path: '/activity', label: 'Activity', icon: '📜' },
  { path: '/system', label: 'System', icon: '⚙️' },
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
        'bg-bg-secondary border-r border-border flex flex-col transition-all duration-200',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Toggle button */}
      <button
        onClick={onToggle}
        className="h-12 flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? '→' : '←'}
      </button>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            aria-label={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-4 py-3 transition-colors',
                'hover:bg-bg-tertiary focus:outline-none focus:ring-2 focus:ring-accent-blue focus:ring-inset',
                isActive
                  ? 'text-accent-blue bg-accent-blue/10 border-r-2 border-accent-blue'
                  : 'text-text-secondary'
              )
            }
          >
            <span className="text-lg" aria-hidden="true">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="p-4 border-t border-border text-text-secondary text-xs">
          v1.0.0
        </div>
      )}
    </aside>
  );
}
