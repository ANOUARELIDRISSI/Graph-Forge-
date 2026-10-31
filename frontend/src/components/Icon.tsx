import type { SVGProps } from 'react';

export type IconName =
  | 'overview'
  | 'graph'
  | 'analytics'
  | 'assistant'
  | 'sources'
  | 'quality'
  | 'pipeline'
  | 'refresh'
  | 'search'
  | 'send'
  | 'plus'
  | 'close'
  | 'external'
  | 'route'
  | 'layers'
  | 'check'
  | 'warning'
  | 'arrowRight';

const PATHS: Record<IconName, string> = {
  overview: 'M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z',
  graph: 'M6 8.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5Zm12 12a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5ZM6 20.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5Zm0-12L18 18M6 15.5V8.5',
  analytics: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  assistant: 'M21 12a8 8 0 0 1-8 8H7l-4 3v-6.5A8 8 0 0 1 11 4h2a8 8 0 0 1 8 8Z',
  sources: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0 0c2.5-2.4 4-5.6 4-9s-1.5-6.6-4-9M12 21c-2.5-2.4-4-5.6-4-9s1.5-6.6 4-9M3.5 9h17M3.5 15h17',
  quality: 'M12 3 4 6v6c0 5 3.4 8.3 8 9.5 4.6-1.2 8-4.5 8-9.5V6l-8-3Zm-2.5 8.5 2 2 4-4',
  pipeline: 'M3 12h4l2.5-7 5 14L17 12h4',
  refresh: 'M20 11a8 8 0 1 0-2.3 6.3M20 5v6h-6',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.35-4.35',
  send: 'M12 19V5M5 12l7-7 7 7',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M18 6L6 18',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  route: 'M6 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm12-8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0 0c0 5-6 3-6 8',
  layers: 'm12 3 9 5-9 5-9-5 9-5Zm9 9-9 5-9-5m18 4-9 5-9-5',
  check: 'M20 6 9 17l-5-5',
  warning: 'M12 9v4m0 4h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
};

type IconProps = SVGProps<SVGSVGElement> & { name: IconName; size?: number };

export function Icon({ name, size = 18, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
