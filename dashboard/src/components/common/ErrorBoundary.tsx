/**
 * Error Boundary Component
 *
 * Catches JavaScript errors anywhere in the child component tree and displays
 * a fallback UI instead of crashing the entire application. Critical for trading
 * dashboards where users must maintain access to positions and controls.
 */
import { Component, type ReactNode, type ErrorInfo } from 'react';
import clsx from 'clsx';

/**
 * Props for the ErrorFallback component
 */
export interface ErrorFallbackProps {
  error: Error;
  errorInfo?: ErrorInfo;
  resetError: () => void;
  componentStack?: string | null;
  className?: string;
}

/**
 * Fallback UI displayed when an error is caught
 */
export function ErrorFallback({
  error,
  errorInfo,
  resetError,
  componentStack,
  className,
}: ErrorFallbackProps) {
  const stackToShow = componentStack || errorInfo?.componentStack;

  return (
    <div
      data-testid="error-fallback"
      className={clsx(
        'flex flex-col items-center justify-center p-8 text-center min-h-[300px]',
        className
      )}
      role="alert"
      aria-live="assertive"
    >
      {/* Error Icon */}
      <div className="w-16 h-16 rounded-full bg-negative/10 flex items-center justify-center mb-4">
        <svg
          className="w-8 h-8 text-negative"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>

      {/* Error Message */}
      <h2 className="text-xl font-semibold text-text-primary mb-2">
        Something went wrong
      </h2>
      <p className="text-text-secondary text-sm mb-6 max-w-md">
        An error occurred while rendering this section. You can try again or navigate
        to another page. Your trading controls remain accessible.
      </p>

      {/* Retry Button */}
      <button
        onClick={resetError}
        className="btn btn-primary mb-6"
        data-testid="error-retry-button"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        Try Again
      </button>

      {/* Collapsible Error Details */}
      <details className="w-full max-w-2xl text-left">
        <summary className="cursor-pointer text-text-muted text-sm hover:text-text-secondary transition-colors select-none">
          Show error details
        </summary>
        <div className="mt-3 p-4 bg-bg-tertiary border border-border rounded-lg overflow-auto">
          <div className="mb-3">
            <span className="text-label text-text-muted text-xs uppercase tracking-wider">
              Error Message
            </span>
            <p className="text-negative text-sm font-mono mt-1 break-words">
              {error.message || 'Unknown error'}
            </p>
          </div>

          {error.name && error.name !== 'Error' && (
            <div className="mb-3">
              <span className="text-label text-text-muted text-xs uppercase tracking-wider">
                Error Type
              </span>
              <p className="text-text-secondary text-sm font-mono mt-1">
                {error.name}
              </p>
            </div>
          )}

          {stackToShow && (
            <div className="mb-3">
              <span className="text-label text-text-muted text-xs uppercase tracking-wider">
                Component Stack
              </span>
              <pre className="text-text-secondary text-xs font-mono mt-1 whitespace-pre-wrap overflow-x-auto">
                {stackToShow}
              </pre>
            </div>
          )}

          {error.stack && (
            <div>
              <span className="text-label text-text-muted text-xs uppercase tracking-wider">
                Stack Trace
              </span>
              <pre className="text-text-secondary text-xs font-mono mt-1 whitespace-pre-wrap overflow-x-auto max-h-48">
                {error.stack}
              </pre>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

/**
 * Props for the ErrorBoundary component
 */
export interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional custom fallback component */
  fallback?: ReactNode | ((props: ErrorFallbackProps) => ReactNode);
  /** Called when an error is caught */
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  /** Called when the error state is reset */
  onReset?: () => void;
  /** Additional CSS classes for the fallback wrapper */
  fallbackClassName?: string;
  /** Unique key to force reset when changed */
  resetKey?: string | number;
}

/**
 * State for the ErrorBoundary component
 */
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Error Boundary class component
 *
 * Wraps children and catches any JavaScript errors that occur during rendering,
 * lifecycle methods, or in constructors of the whole tree below.
 *
 * Usage:
 * ```tsx
 * <ErrorBoundary>
 *   <ComponentThatMightError />
 * </ErrorBoundary>
 * ```
 *
 * With custom fallback:
 * ```tsx
 * <ErrorBoundary fallback={<CustomErrorUI />}>
 *   <ComponentThatMightError />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // Update state so the next render shows the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log error to console for debugging
    console.error('[ErrorBoundary] Caught error:', error);
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);

    // Update state with error info
    this.setState({ errorInfo });

    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    // Reset error state when resetKey changes
    if (
      this.state.hasError &&
      prevProps.resetKey !== this.props.resetKey
    ) {
      this.resetError();
    }
  }

  resetError = (): void => {
    this.props.onReset?.();
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render(): ReactNode {
    const { hasError, error, errorInfo } = this.state;
    const { children, fallback, fallbackClassName } = this.props;

    if (hasError && error) {
      // If a custom fallback is provided as a function, call it with error props
      if (typeof fallback === 'function') {
        return fallback({
          error,
          errorInfo: errorInfo || undefined,
          resetError: this.resetError,
          componentStack: errorInfo?.componentStack,
          className: fallbackClassName,
        });
      }

      // If a custom fallback is provided as a ReactNode, render it
      if (fallback !== undefined) {
        return fallback;
      }

      // Default fallback UI
      return (
        <ErrorFallback
          error={error}
          errorInfo={errorInfo || undefined}
          resetError={this.resetError}
          componentStack={errorInfo?.componentStack}
          className={fallbackClassName}
        />
      );
    }

    return children;
  }
}

/**
 * Higher-order component to wrap a component with an ErrorBoundary
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  errorBoundaryProps?: Omit<ErrorBoundaryProps, 'children'>
) {
  const displayName = WrappedComponent.displayName || WrappedComponent.name || 'Component';

  const ComponentWithErrorBoundary = (props: P) => (
    <ErrorBoundary {...errorBoundaryProps}>
      <WrappedComponent {...props} />
    </ErrorBoundary>
  );

  ComponentWithErrorBoundary.displayName = `withErrorBoundary(${displayName})`;

  return ComponentWithErrorBoundary;
}

export default ErrorBoundary;
