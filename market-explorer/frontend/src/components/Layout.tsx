import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BarChart3, Search, Star, Settings, Layers } from 'lucide-react'

interface LayoutProps {
  children: ReactNode
}

const navItems = [
  { path: '/', label: 'Markets', icon: BarChart3 },
  { path: '/events', label: 'Events', icon: Layers },
  { path: '/watchlist', label: 'Watchlist', icon: Star },
  { path: '/settings', label: 'Settings', icon: Settings },
]

export function Layout({ children }: LayoutProps) {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-gray-900 flex">
      {/* Sidebar */}
      <aside className="w-16 lg:w-56 bg-gray-800 border-r border-gray-700 flex-shrink-0">
        <div className="p-4">
          <h1 className="hidden lg:block text-xl font-bold text-pm-green">
            Market Explorer
          </h1>
          <div className="lg:hidden text-pm-green text-2xl font-bold text-center">
            ME
          </div>
        </div>

        <nav className="mt-4">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`
                  flex items-center gap-3 px-4 py-3 text-sm
                  ${isActive
                    ? 'bg-gray-700 text-white border-l-2 border-pm-green'
                    : 'text-gray-400 hover:text-white hover:bg-gray-750'
                  }
                `}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span className="hidden lg:block">{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center px-4 gap-4">
          <div className="flex-1 max-w-md">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search markets..."
                className="w-full bg-gray-700 text-white rounded-lg pl-10 pr-4 py-2 text-sm
                         placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-pm-green"
              />
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm text-gray-400">
            <span className="hidden md:inline">Last updated:</span>
            <span className="text-white">Just now</span>
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 overflow-auto p-4">
          {children}
        </div>
      </main>
    </div>
  )
}
