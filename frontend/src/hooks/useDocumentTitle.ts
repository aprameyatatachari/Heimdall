import { useEffect } from "react";

/** Set the tab title. The brand name is always in Latin, never runes. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title ? `${title} — Heimdall` : "Heimdall";
  }, [title]);
}
