import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "@/auth/AuthProvider";
import { SkipLink } from "@/components/SkipLink";

import { ErrorBoundary } from "./ErrorBoundary";
import { createQueryClient } from "./queryClient";
import { AppRoutes } from "./routes";

export function App() {
  // Created once per mount so each test renders against its own cache.
  const [queryClient] = useState(createQueryClient);

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <SkipLink />
            <AppRoutes />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
