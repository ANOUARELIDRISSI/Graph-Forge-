import { QueryClient } from '@tanstack/react-query';
export const queryClient=new QueryClient({defaultOptions:{queries:{staleTime:60000,gcTime:30*60000,retry:2,retryDelay:n=>Math.min(1000*2**n,8000),refetchOnWindowFocus:false}}});
