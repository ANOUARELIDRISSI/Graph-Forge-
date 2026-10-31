export const NODE_COLORS: Record<string, string> = {
  Source: '#6366f1',
  Page: '#0ea5e9',
  Sector: '#10b981',
  Country: '#f59e0b',
  Region: '#ec4899',
  Organization: '#8b5cf6',
  Entity: '#64748b',
};

export const NODE_SIZES: Record<string, number> = {
  Sector: 7,
  Country: 7,
  Region: 6.5,
  Organization: 6.5,
  Page: 4.5,
  Source: 6,
  Entity: 4.5,
};

export const nodeColor = (label: string): string => NODE_COLORS[label] ?? '#64748b';
export const nodeRadius = (label: string): number => NODE_SIZES[label] ?? 5;
