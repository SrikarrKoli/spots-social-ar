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
      if (typeof document !== "undefined" && document.hidden) return;
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

    const onVisibilityChange = () => {
      if (disposed || typeof document === "undefined") return;
      if (timeout) {
        window.clearTimeout(timeout);
        timeout = undefined;
      }
      if (document.hidden) {
        controller?.abort();
      } else {
        void poll();
      }
    };

    void poll();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      disposed = true;
      if (timeout) window.clearTimeout(timeout);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [enabled, intervalMs]);
}
