import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { createQueryClient } from "@/app/queryClient";
import { AuthProvider } from "@/auth/AuthProvider";

/** Render inside the providers every screen depends on, at a chosen route. */
export function renderApp(
  ui: ReactElement,
  { route = "/" }: { route?: string } = {},
): RenderResult & { user: ReturnType<typeof userEvent.setup> } {
  const queryClient = createQueryClient();
  // Retries would turn one deliberate failure into three and slow every test.
  queryClient.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });

  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>{ui}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...result, user: userEvent.setup() };
}
