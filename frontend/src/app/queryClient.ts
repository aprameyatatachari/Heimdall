import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/errors";

/**
 * Query defaults.
 *
 * A 4xx is the server's considered answer, not a transient fault — retrying it
 * only delays the message the user needs. Network and 5xx failures retry twice.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status < 500) return false;
          return failureCount < 2;
        },
      },
      mutations: { retry: false },
    },
  });
}
