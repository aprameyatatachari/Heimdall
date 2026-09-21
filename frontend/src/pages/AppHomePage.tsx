import { Panel } from "@/components/Panel";
import { useAuth } from "@/auth/useAuth";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

/**
 * The authenticated landing surface.
 *
 * Phase 8 builds the foundation only: no portfolio, analytics, stress-test,
 * signal or report screens exist yet. This page says plainly what is and is not
 * built rather than showing a shell full of empty widgets.
 */
export function AppHomePage() {
  useDocumentTitle("Home");
  const { user } = useAuth();

  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className="hm-eyebrow mb-3">Signed in</p>
        <h1 className="font-display text-ink text-[length:var(--text-2xl)] font-light">
          Your watch
        </h1>
        <p className="text-ink-muted mt-2 text-sm">{user?.email}</p>
      </div>

      <Panel>
        <h2 className="text-ink text-lg font-medium">The watch is being built</h2>
        <p className="text-ink-muted mt-3 max-w-prose text-sm leading-relaxed">
          Authentication, routing, the API client and the application shell are in place.
          Portfolios, analytics, stress testing, Gjallarhorn signals and reports arrive in the
          phases that follow — each built against the API contracts the backend already
          publishes.
        </p>
      </Panel>
    </div>
  );
}
