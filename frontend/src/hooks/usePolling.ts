import { useEffect, useRef } from "react";

export function usePolling(
  callback: (signal: AbortSignal) => Promise<void>,
  intervalMs: number,
  enabled = true,
) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let timeout: number | undefined;
    let controller: AbortController | undefined;

    const poll = async () => {
      controller = new AbortController();
      try {
        await callbackRef.current(controller.signal);
      } catch (error) {
        if (!disposed && !(error instanceof DOMException && error.name === "AbortError")) {
          // The owning view decides how to display polling failures.
        }
      }
      if (!disposed) timeout = window.setTimeout(poll, intervalMs);
    };

    void poll();
    return () => {
      disposed = true;
      if (timeout) window.clearTimeout(timeout);
      controller?.abort();
    };
  }, [enabled, intervalMs]);
}
