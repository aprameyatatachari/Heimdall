import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/Button";
import { Star } from "@/components/Star";

interface State {
  error: Error | null;
}

/**
 * Last line of defence for a render-time failure.
 *
 * The user is told that something broke and offered a way forward. The error's
 * own message is never shown — it can carry internal detail, and it is never
 * anything a user can act on. AGENTS.md section 1 rule 6.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept to the console deliberately: there is no error-reporting service
    // configured, and inventing one would ship user data off-site.
    console.error("Unhandled rendering error", error, info.componentStack);
  }

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;

    return (
      <div className="flex min-h-dvh flex-col items-center justify-center px-4 text-center">
        <Star className="text-ink-faint mb-6 size-8" />
        <h1 className="font-display text-ink text-[length:var(--text-2xl)] font-light">
          Something went wrong
        </h1>
        <p className="text-ink-muted mt-3 max-w-md text-sm">
          Heimdall could not finish drawing this page. Your data is unaffected.
        </p>
        <div className="mt-8 flex gap-3">
          <Button onClick={() => this.setState({ error: null })} variant="secondary">
            Try again
          </Button>
          <Button onClick={() => window.location.assign("/")}>Return to the start</Button>
        </div>
      </div>
    );
  }
}
