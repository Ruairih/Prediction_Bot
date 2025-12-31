/**
 * Skeleton Loading Components
 *
 * Reusable skeleton loaders that match the layout of content being loaded.
 * Uses the existing .skeleton CSS class from index.css with shimmer animation.
 */
import clsx from 'clsx';

// ============================================================================
// Base Skeleton
// ============================================================================

export interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: 'none' | 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'full';
}

export function Skeleton({
  className,
  width,
  height,
  rounded = 'md',
}: SkeletonProps) {
  const roundedClasses = {
    none: 'rounded-none',
    sm: 'rounded-sm',
    md: 'rounded-md',
    lg: 'rounded-lg',
    xl: 'rounded-xl',
    '2xl': 'rounded-2xl',
    full: 'rounded-full',
  };

  return (
    <div
      className={clsx('skeleton', roundedClasses[rounded], className)}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
      }}
      aria-hidden="true"
    />
  );
}

// ============================================================================
// SkeletonText - For text lines
// ============================================================================

export interface SkeletonTextProps {
  lines?: number;
  className?: string;
  widths?: (string | number)[];
}

export function SkeletonText({
  lines = 1,
  className,
  widths = ['100%', '80%', '60%'],
}: SkeletonTextProps) {
  return (
    <div className={clsx('space-y-2', className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height={16}
          width={widths[i % widths.length]}
          rounded="sm"
        />
      ))}
    </div>
  );
}

// ============================================================================
// SkeletonCard - For card-shaped areas
// ============================================================================

export interface SkeletonCardProps {
  className?: string;
  height?: string | number;
  hasHeader?: boolean;
  hasBody?: boolean;
  bodyLines?: number;
}

export function SkeletonCard({
  className,
  height,
  hasHeader = true,
  hasBody = true,
  bodyLines = 3,
}: SkeletonCardProps) {
  return (
    <div
      className={clsx(
        'bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm',
        className
      )}
      style={{ height: typeof height === 'number' ? `${height}px` : height }}
      aria-hidden="true"
    >
      {hasHeader && (
        <div className="mb-4">
          <Skeleton height={12} width={80} className="mb-2" rounded="sm" />
          <Skeleton height={24} width={160} rounded="md" />
        </div>
      )}
      {hasBody && <SkeletonText lines={bodyLines} />}
    </div>
  );
}

// ============================================================================
// SkeletonKPI - For KPI tiles
// ============================================================================

export interface SkeletonKPIProps {
  className?: string;
}

export function SkeletonKPI({ className }: SkeletonKPIProps) {
  return (
    <div
      className={clsx(
        'kpi-tile relative overflow-hidden',
        className
      )}
      aria-hidden="true"
    >
      {/* Label */}
      <Skeleton height={10} width={60} className="mb-3" rounded="sm" />

      {/* Value */}
      <Skeleton height={32} width={100} className="mb-2" rounded="md" />

      {/* Change indicator */}
      <div className="flex items-center gap-2">
        <Skeleton height={12} width={12} rounded="full" />
        <Skeleton height={14} width={50} rounded="sm" />
      </div>
    </div>
  );
}

// ============================================================================
// SkeletonTable - For table rows
// ============================================================================

export interface SkeletonTableProps {
  columns: number;
  rows?: number;
  className?: string;
  columnWidths?: (string | number)[];
}

export function SkeletonTable({
  columns,
  rows = 5,
  className,
  columnWidths,
}: SkeletonTableProps) {
  const defaultWidths = ['40%', '20%', '15%', '15%', '10%'];

  return (
    <div
      className={clsx(
        'bg-bg-secondary rounded-2xl border border-border shadow-sm overflow-hidden',
        className
      )}
      aria-hidden="true"
    >
      {/* Header */}
      <div className="flex items-center gap-4 px-4 py-3 bg-bg-tertiary border-b border-border">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton
            key={i}
            height={12}
            width={columnWidths?.[i] ?? defaultWidths[i % defaultWidths.length]}
            rounded="sm"
            className="flex-shrink-0"
          />
        ))}
      </div>

      {/* Rows */}
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <div key={rowIndex} className="flex items-center gap-4 px-4 py-4">
            {Array.from({ length: columns }).map((_, colIndex) => (
              <Skeleton
                key={colIndex}
                height={16}
                width={columnWidths?.[colIndex] ?? defaultWidths[colIndex % defaultWidths.length]}
                rounded="sm"
                className="flex-shrink-0"
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// SkeletonActivityItem - For activity stream items
// ============================================================================

export interface SkeletonActivityItemProps {
  className?: string;
}

export function SkeletonActivityItem({ className }: SkeletonActivityItemProps) {
  return (
    <div
      className={clsx(
        'flex items-start gap-3 p-3 rounded-xl border-l-2 border-l-text-secondary border border-border/60',
        className
      )}
      aria-hidden="true"
    >
      {/* Icon */}
      <Skeleton height={24} width={24} rounded="md" />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <Skeleton height={16} width="80%" className="mb-2" rounded="sm" />
        <Skeleton height={12} width={80} rounded="sm" />
      </div>
    </div>
  );
}

// ============================================================================
// SkeletonActivityStream - For activity stream container
// ============================================================================

export interface SkeletonActivityStreamProps {
  items?: number;
  className?: string;
}

export function SkeletonActivityStream({
  items = 5,
  className,
}: SkeletonActivityStreamProps) {
  return (
    <div
      className={clsx(
        'bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm',
        className
      )}
      aria-hidden="true"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <Skeleton height={10} width={60} className="mb-2" rounded="sm" />
          <Skeleton height={20} width={100} rounded="md" />
        </div>
        <Skeleton height={14} width={60} rounded="sm" />
      </div>

      {/* Items */}
      <div className="space-y-2">
        {Array.from({ length: items }).map((_, i) => (
          <SkeletonActivityItem key={i} />
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// SkeletonPositionsSummary - For positions summary cards
// ============================================================================

export function SkeletonPositionsSummary() {
  return (
    <div
      className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6"
      aria-hidden="true"
    >
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm"
        >
          <Skeleton height={14} width={100} className="mb-2" rounded="sm" />
          <Skeleton height={32} width={80} rounded="md" />
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// SkeletonActivityStats - For activity stats bar
// ============================================================================

export function SkeletonActivityStats() {
  return (
    <div className="flex flex-wrap gap-4 mb-6" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="bg-bg-secondary rounded-lg px-4 py-2 border border-border flex items-center gap-2"
        >
          <Skeleton height={14} width={60} rounded="sm" />
          <Skeleton height={18} width={30} rounded="sm" />
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// SkeletonChart - For chart placeholders
// ============================================================================

export interface SkeletonChartProps {
  height?: number;
  className?: string;
}

export function SkeletonChart({ height = 300, className }: SkeletonChartProps) {
  return (
    <div
      className={clsx(
        'bg-bg-secondary rounded-2xl p-4 border border-border shadow-sm',
        className
      )}
      aria-hidden="true"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <Skeleton height={10} width={80} className="mb-2" rounded="sm" />
          <Skeleton height={20} width={140} rounded="md" />
        </div>
        <div className="flex gap-2">
          <Skeleton height={28} width={60} rounded="md" />
          <Skeleton height={28} width={60} rounded="md" />
        </div>
      </div>

      {/* Chart area */}
      <div
        className="flex items-end justify-between gap-2 px-4"
        style={{ height }}
      >
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton
            key={i}
            width="100%"
            height={`${30 + Math.random() * 60}%`}
            rounded="sm"
            className="flex-1"
          />
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Compound loading state components
// ============================================================================

/**
 * Full page loading skeleton for Overview page
 */
export function SkeletonOverview() {
  return (
    <div className="px-6 py-6 space-y-6" aria-busy="true" aria-label="Loading dashboard">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Skeleton height={12} width={120} className="mb-2" rounded="sm" />
          <Skeleton height={36} width={280} className="mb-2" rounded="md" />
          <Skeleton height={16} width={320} rounded="sm" />
        </div>
        <Skeleton height={40} width={140} rounded="full" />
      </div>

      {/* KPI Tiles */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonKPI key={i} />
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activity Stream */}
        <div className="lg:col-span-2 space-y-6">
          <SkeletonActivityStream items={5} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <SkeletonCard bodyLines={4} />
            <SkeletonCard bodyLines={4} />
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <SkeletonCard height={200} bodyLines={5} />
          <SkeletonCard bodyLines={4} />
        </div>
      </div>

      {/* Chart */}
      <SkeletonChart />
    </div>
  );
}

/**
 * Full page loading skeleton for Positions page
 */
export function SkeletonPositions() {
  return (
    <div className="px-6 py-6 space-y-6" aria-busy="true" aria-label="Loading positions">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Skeleton height={12} width={80} className="mb-2" rounded="sm" />
          <Skeleton height={36} width={220} className="mb-2" rounded="md" />
          <Skeleton height={16} width={280} rounded="sm" />
        </div>
        <div className="flex items-center gap-3">
          <Skeleton height={40} width={80} rounded="full" />
          <Skeleton height={40} width={100} rounded="full" />
          <Skeleton height={40} width={80} rounded="full" />
        </div>
      </div>

      {/* Summary */}
      <SkeletonPositionsSummary />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <Skeleton height={40} width={200} rounded="lg" />
        <Skeleton height={40} width={120} rounded="lg" />
        <Skeleton height={40} width={120} rounded="lg" />
      </div>

      {/* Table */}
      <SkeletonTable columns={6} rows={8} />
    </div>
  );
}

/**
 * Full page loading skeleton for Activity page
 */
export function SkeletonActivity() {
  return (
    <div className="p-6 space-y-6" aria-busy="true" aria-label="Loading activity">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <Skeleton height={32} width={120} className="mb-2" rounded="md" />
          <Skeleton height={16} width={280} rounded="sm" />
        </div>
      </div>

      {/* Stats */}
      <SkeletonActivityStats />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <Skeleton height={40} width={240} rounded="lg" />
        <Skeleton height={40} width={140} rounded="lg" />
        <Skeleton height={40} width={140} rounded="lg" />
        <Skeleton height={40} width={100} rounded="lg" />
      </div>

      {/* Activity List */}
      <div className="space-y-2">
        {Array.from({ length: 10 }).map((_, i) => (
          <SkeletonActivityItem key={i} />
        ))}
      </div>

      {/* Pagination */}
      <div className="flex justify-center gap-2">
        <Skeleton height={36} width={80} rounded="md" />
        <Skeleton height={36} width={36} rounded="md" />
        <Skeleton height={36} width={36} rounded="md" />
        <Skeleton height={36} width={36} rounded="md" />
        <Skeleton height={36} width={80} rounded="md" />
      </div>
    </div>
  );
}
