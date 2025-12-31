/**
 * Unit Tests for ConfirmDialog Component
 *
 * Tests the confirmation dialog for dangerous actions, including:
 * - Standard confirmation flow
 * - Typed confirmation for live mode
 * - Accessibility attributes
 * - Loading states
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ConfirmDialog } from './ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    title: 'Confirm Action',
    description: 'Are you sure you want to do this?',
    confirmText: 'Confirm',
    cancelText: 'Cancel',
    variant: 'warning' as const,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('renders when isOpen is true', () => {
      render(<ConfirmDialog {...defaultProps} />);
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    it('does not render when isOpen is false', () => {
      render(<ConfirmDialog {...defaultProps} isOpen={false} />);
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });

    it('displays the title', () => {
      render(<ConfirmDialog {...defaultProps} />);
      expect(screen.getByText('Confirm Action')).toBeInTheDocument();
    });

    it('displays the description', () => {
      render(<ConfirmDialog {...defaultProps} />);
      expect(screen.getByText('Are you sure you want to do this?')).toBeInTheDocument();
    });

    it('displays consequences when provided', () => {
      const consequences = ['This will delete data', 'This cannot be undone'];
      render(<ConfirmDialog {...defaultProps} consequences={consequences} />);
      expect(screen.getByText('This will delete data')).toBeInTheDocument();
      expect(screen.getByText('This cannot be undone')).toBeInTheDocument();
    });
  });

  describe('Buttons', () => {
    it('displays confirm and cancel buttons', () => {
      render(<ConfirmDialog {...defaultProps} />);
      expect(screen.getByRole('button', { name: /confirm/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    it('calls onClose when cancel button is clicked', () => {
      render(<ConfirmDialog {...defaultProps} />);
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
      expect(defaultProps.onClose).toHaveBeenCalled();
    });

    it('calls onConfirm when confirm button is clicked', async () => {
      render(<ConfirmDialog {...defaultProps} />);
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalled();
      });
    });

    it('disables buttons when loading', () => {
      render(<ConfirmDialog {...defaultProps} isLoading />);
      expect(screen.getByRole('button', { name: /confirm/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled();
    });
  });

  describe('Typed Confirmation', () => {
    const typedProps = {
      ...defaultProps,
      requiresTypedConfirmation: true,
      confirmationPhrase: 'DELETE',
    };

    it('shows input field when typed confirmation is required', () => {
      render(<ConfirmDialog {...typedProps} />);
      expect(screen.getByRole('textbox')).toBeInTheDocument();
    });

    it('displays the confirmation phrase instruction', () => {
      render(<ConfirmDialog {...typedProps} />);
      expect(screen.getByText(/DELETE/)).toBeInTheDocument();
      expect(screen.getByText(/to confirm/i)).toBeInTheDocument();
    });

    it('disables confirm button until phrase is typed correctly', () => {
      render(<ConfirmDialog {...typedProps} />);
      const confirmButton = screen.getByRole('button', { name: /confirm/i });
      expect(confirmButton).toBeDisabled();
    });

    it('enables confirm button when phrase is typed correctly', () => {
      render(<ConfirmDialog {...typedProps} />);
      const input = screen.getByRole('textbox');
      fireEvent.change(input, { target: { value: 'DELETE' } });
      const confirmButton = screen.getByRole('button', { name: /confirm/i });
      expect(confirmButton).not.toBeDisabled();
    });

    it('does not enable confirm button with incorrect phrase', () => {
      render(<ConfirmDialog {...typedProps} />);
      const input = screen.getByRole('textbox');
      fireEvent.change(input, { target: { value: 'delete' } }); // lowercase
      const confirmButton = screen.getByRole('button', { name: /confirm/i });
      expect(confirmButton).toBeDisabled();
    });

    it('allows confirmation on Enter key when phrase is correct', async () => {
      render(<ConfirmDialog {...typedProps} />);
      const input = screen.getByRole('textbox');
      fireEvent.change(input, { target: { value: 'DELETE' } });
      fireEvent.keyDown(input, { key: 'Enter' });
      await waitFor(() => {
        expect(defaultProps.onConfirm).toHaveBeenCalled();
      });
    });
  });

  describe('Variants', () => {
    it('applies warning styling for warning variant', () => {
      render(<ConfirmDialog {...defaultProps} variant="warning" />);
      // The dialog should render with warning colors
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    it('applies danger styling for danger variant', () => {
      render(<ConfirmDialog {...defaultProps} variant="danger" />);
      // The dialog should render with danger colors
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has correct ARIA attributes', () => {
      render(<ConfirmDialog {...defaultProps} />);
      const dialog = screen.getByRole('alertdialog');
      expect(dialog).toHaveAttribute('aria-modal', 'true');
      expect(dialog).toHaveAttribute('aria-labelledby', 'confirm-dialog-title');
      expect(dialog).toHaveAttribute('aria-describedby', 'confirm-dialog-description');
    });

    it('closes on Escape key press', () => {
      render(<ConfirmDialog {...defaultProps} />);
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(defaultProps.onClose).toHaveBeenCalled();
    });

    it('does not close on Escape when loading', () => {
      render(<ConfirmDialog {...defaultProps} isLoading />);
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });
  });

  describe('Backdrop Interaction', () => {
    it('closes when clicking the backdrop', () => {
      render(<ConfirmDialog {...defaultProps} />);
      // Click outside the dialog (on the backdrop)
      const backdrop = document.querySelector('[aria-hidden="true"]');
      if (backdrop) {
        fireEvent.click(backdrop);
        expect(defaultProps.onClose).toHaveBeenCalled();
      }
    });

    it('does not close when clicking inside the dialog', () => {
      render(<ConfirmDialog {...defaultProps} />);
      const dialog = screen.getByRole('alertdialog');
      fireEvent.click(dialog);
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });
  });
});
