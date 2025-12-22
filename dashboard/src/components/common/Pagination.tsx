/**
 * Pagination Component
 */
import clsx from 'clsx';

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize);
  const hasPrevious = page > 1;
  const hasNext = page < totalPages;

  if (totalPages <= 1) {
    return null;
  }

  return (
    <div
      data-testid="pagination"
      className="flex items-center justify-between px-4 py-3 border-t border-border"
    >
      <div className="text-sm text-text-secondary">
        Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={!hasPrevious}
          aria-label="Previous page"
          className={clsx(
            'px-3 py-1 rounded-lg text-sm transition-colors',
            hasPrevious
              ? 'bg-bg-tertiary text-text-primary hover:bg-bg-tertiary/80'
              : 'bg-bg-tertiary/50 text-text-secondary cursor-not-allowed'
          )}
        >
          Previous
        </button>

        <span className="text-sm text-text-secondary px-2">
          Page {page} of {totalPages}
        </span>

        <button
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext}
          aria-label="Next page"
          className={clsx(
            'px-3 py-1 rounded-lg text-sm transition-colors',
            hasNext
              ? 'bg-bg-tertiary text-text-primary hover:bg-bg-tertiary/80'
              : 'bg-bg-tertiary/50 text-text-secondary cursor-not-allowed'
          )}
        >
          Next
        </button>
      </div>
    </div>
  );
}
