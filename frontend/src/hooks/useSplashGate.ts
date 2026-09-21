import { useCallback, useState } from "react";

const KEY = "heimdall.gate";

/**
 * Whether the gate should be shown.
 *
 * Once per browser session: ceremony on arrival, nothing in the way of someone
 * who comes back six times in an afternoon. Session storage rather than local
 * storage, so a new session earns the gate again.
 *
 * Reading it can throw in a private window or with site data blocked, and the
 * gate is decoration — a storage failure shows it, it never breaks the page.
 */
function alreadyEntered(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === "entered";
  } catch {
    return false;
  }
}

export function useSplashGate(): { showGate: boolean; markEntered: () => void } {
  // Decided once on mount. Flipping it mid-visit would unmount the scroll
  // runway under the reader.
  const [showGate] = useState(() => !alreadyEntered());

  const markEntered = useCallback(() => {
    try {
      window.sessionStorage.setItem(KEY, "entered");
    } catch {
      // Nothing to recover: the gate simply appears again next time.
    }
    // The section stays mounted for the rest of this visit. Removing it here
    // would delete the scroll runway under the reader and jump the page.
  }, []);

  return { showGate, markEntered };
}
