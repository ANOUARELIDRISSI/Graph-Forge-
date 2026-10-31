import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Badge, Card, EmptyState, ErrorState, Meter, StatCard } from './ui';

describe('Badge', () => {
  it('defaults to the neutral tone', () => {
    render(<Badge>status</Badge>);
    expect(screen.getByText('status')).toHaveClass('badge', 'badge--neutral');
  });

  it('applies the requested tone', () => {
    render(<Badge tone="ok">online</Badge>);
    expect(screen.getByText('online')).toHaveClass('badge--ok');
  });
});

describe('Meter', () => {
  const widthOf = (value: number, max: number) => {
    const { container } = render(<Meter value={value} max={max} />);
    return container.querySelector('.meter-fill')?.getAttribute('style') ?? '';
  };

  it('renders the ratio as a percentage width', () => {
    expect(widthOf(2, 4)).toContain('50%');
  });

  it('clamps values above max to 100%', () => {
    expect(widthOf(9, 4)).toContain('100%');
  });

  it('clamps negative values to 0%', () => {
    expect(widthOf(-3, 4)).toContain('0%');
  });

  it('guards against a non-positive max', () => {
    expect(widthOf(5, 0)).toContain('0%');
  });
});

describe('StatCard', () => {
  it('renders the label, value and hint', () => {
    render(<StatCard label="Documents" value={42} hint="reviewed sources" />);
    expect(screen.getByText('Documents')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('reviewed sources')).toBeInTheDocument();
  });
});

describe('Card', () => {
  it('omits the header when neither title nor actions are provided', () => {
    const { container } = render(<Card>body</Card>);
    expect(container.querySelector('.card-head')).toBeNull();
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('renders the header when a title is provided', () => {
    render(<Card title="Pipeline">body</Card>);
    expect(screen.getByRole('heading', { name: 'Pipeline' })).toBeInTheDocument();
  });
});

describe('EmptyState', () => {
  it('renders the title and description', () => {
    render(<EmptyState title="No documents" description="Crawl a source to begin" />);
    expect(screen.getByRole('heading', { name: 'No documents' })).toBeInTheDocument();
    expect(screen.getByText('Crawl a source to begin')).toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('renders the message and invokes retry', () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Request failed" onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Request failed');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('hides the retry button when no handler is given', () => {
    render(<ErrorState message="Request failed" />);
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  });
});
