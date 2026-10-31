import 'react';

declare module 'react' {
  function useRef<T = undefined>(): MutableRefObject<T | undefined>;
}
