/**
 * Activity Detail Panel
 *
 * Structured view of a selected activity event.
 */
import { useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import type { ActivityEvent } from '../../types';

interface ActivityDetailPanelProps {
  event: ActivityEvent;
  onClose: () => void;
}

interface DetailField {
  label: string;
  value: string;
}

export function ActivityDetailPanel({ event, onClose }: ActivityDetailPanelProps) {
  const highlights = getEventHighlights(event);
  const conditionId = readString(event.details, ['conditionId', 'condition_id']);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previouslyFocusedElement = useRef<HTMLElement | null>(null);

  // Handle Escape key to close the panel
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  }, [onClose]);

  // Focus trap: keep focus within the panel
  const handleFocusTrap = useCallback((e: KeyboardEvent) => {
    if (e.key !== 'Tab' || !panelRef.current) return;

    const focusableElements = panelRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (e.shiftKey && document.activeElement === firstElement) {
      e.preventDefault();
      lastElement?.focus();
    } else if (!e.shiftKey && document.activeElement === lastElement) {
      e.preventDefault();
      firstElement?.focus();
    }
  }, []);

  useEffect(() => {
    // Store the previously focused element
    previouslyFocusedElement.current = document.activeElement as HTMLElement;

    // Focus the close button when panel opens
    closeButtonRef.current?.focus();

    // Add event listeners
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keydown', handleFocusTrap);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keydown', handleFocusTrap);
      // Restore focus to previously focused element
      previouslyFocusedElement.current?.focus();
    };
  }, [handleKeyDown, handleFocusTrap]);

  return (
    <div
      ref={panelRef}
      data-testid="activity-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="activity-panel-title"
      className="fixed inset-y-0 right-0 w-96 bg-bg-secondary border-l border-border shadow-xl z-50"
    >
      <div className="flex items-center justify-between p-4 border-b border-border">
        <h3 id="activity-panel-title" className="text-lg font-semibold text-text-primary">Event Details</h3>
        <button
          ref={closeButtonRef}
          onClick={onClose}
          aria-label="Close event details panel"
          className="text-text-secondary hover:text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-blue rounded p-1"
        >
          X
        </button>
      </div>
      <div className="p-4 space-y-4">
        <div>
          <span className="text-xs text-text-secondary uppercase">Type</span>
          <p className="text-text-primary">{event.type.replace(/_/g, ' ')}</p>
        </div>
        <div>
          <span className="text-xs text-text-secondary uppercase">Timestamp</span>
          <p className="text-text-primary">{new Date(event.timestamp).toLocaleString()}</p>
        </div>
        <div>
          <span className="text-xs text-text-secondary uppercase">Summary</span>
          <p className="text-text-primary">{event.summary}</p>
        </div>

        {highlights.length > 0 && (
          <div>
            <span className="text-xs text-text-secondary uppercase">Highlights</span>
            <div className="mt-2 grid grid-cols-1 gap-3">
              {highlights.map((field) => (
                <div key={field.label} className="rounded-lg border border-border bg-bg-tertiary/60 p-3">
                  <div className="text-[10px] uppercase tracking-wide text-text-secondary/70">{field.label}</div>
                  <div className="text-sm text-text-primary">{field.value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {conditionId && (
          <div>
            <span className="text-xs text-text-secondary uppercase">Market</span>
            <Link
              to={`/markets?conditionId=${encodeURIComponent(conditionId)}`}
              className="block mt-1 text-accent-blue hover:text-accent-blue/80 transition-colors"
              onClick={onClose}
            >
              View Market Details &rarr;
            </Link>
          </div>
        )}

        <div>
          <span className="text-xs text-text-secondary uppercase">Raw Details</span>
          <pre className="mt-2 p-3 bg-bg-tertiary rounded text-xs overflow-auto text-text-primary">
            {JSON.stringify(event.details, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

function getEventHighlights(event: ActivityEvent): DetailField[] {
  const details = event.details ?? {};
  const fields: DetailField[] = [];

  const addField = (label: string, value: string | null) => {
    if (!value || value === '-') return;
    fields.push({ label, value });
  };

  if (event.type === 'signal') {
    addField('Token', readString(details, ['token_id', 'tokenId']));
    addField('Condition', readString(details, ['condition_id', 'conditionId']));
    addField('Price', formatPrice(readNumber(details, ['price'])));
    addField('Trade size', formatNumber(readNumber(details, ['trade_size', 'tradeSize']), 0));
    addField('Model score', formatScore(readNumber(details, ['model_score', 'modelScore'])));
  }

  if (event.type.startsWith('order_')) {
    addField('Order', readString(details, ['order_id', 'orderId']));
    addField('Side', readString(details, ['side']));
    addField('Size', formatNumber(readNumber(details, ['size']), 0));
    addField('Price', formatPrice(readNumber(details, ['price'])));
    addField('Status', readString(details, ['status']));
  }

  if (event.type === 'position_opened') {
    addField('Position', readString(details, ['position_id', 'positionId']));
    addField('Entry price', formatPrice(readNumber(details, ['entry_price', 'entryPrice'])));
    addField('Size', formatNumber(readNumber(details, ['size']), 0));
  }

  if (event.type === 'position_closed') {
    addField('Position', readString(details, ['position_id', 'positionId']));
    addField('Exit price', formatPrice(readNumber(details, ['exit_price', 'exitPrice'])));
    addField('Size', formatNumber(readNumber(details, ['size']), 0));
    addField('PnL', formatSignedCurrency(readNumber(details, ['pnl'])));
    addField('Reason', readString(details, ['reason']));
  }

  if (fields.length === 0) {
    addField('Reference', readString(details, ['id', 'order_id', 'position_id']));
    addField('Reason', readString(details, ['reason']));
  }

  return fields;
}

function readString(details: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = details[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return null;
}

function readNumber(details: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = details[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) {
      return Number(value);
    }
  }
  return null;
}

function formatPrice(value: number | null): string | null {
  if (value === null) return null;
  return `$${value.toFixed(3)}`;
}

function formatNumber(value: number | null, digits = 2): string | null {
  if (value === null) return null;
  return value.toFixed(digits);
}

function formatScore(value: number | null): string | null {
  if (value === null) return null;
  if (value <= 1) return `${(value * 100).toFixed(1)}%`;
  return `${value.toFixed(1)}%`;
}

function formatSignedCurrency(value: number | null): string | null {
  if (value === null) return null;
  const sign = value >= 0 ? '+' : '';
  return `${sign}$${value.toFixed(2)}`;
}
