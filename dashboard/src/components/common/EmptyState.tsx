/**
 * Empty State Component
 * Displays when no data is available
 */
import clsx from 'clsx';

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({ title, description, icon = '📭', action, className }: EmptyStateProps) {
  return (
    <div
      data-testid="empty-state"
      className={clsx(
        'flex flex-col items-center justify-center py-12 text-center',
        className
      )}
    >
      <span className="text-4xl mb-4" aria-hidden="true">{icon}</span>
      <h3 className="text-lg font-semibold text-text-primary mb-2">{title}</h3>
      {description && (
        <p className="text-text-secondary text-sm max-w-md">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 px-4 py-2 bg-accent-blue text-white rounded-lg hover:bg-accent-blue/80 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
