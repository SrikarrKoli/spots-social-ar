import { useCallback, useState } from "react";
import { api } from "../api";
import type { ObjectSummary, ThreadResponse } from "../types";
import { useLiveUpdates } from "./useLiveUpdates";
import { usePolling } from "./usePolling";

export function useThreads(objects: ObjectSummary[]) {
  const [threads, setThreads] = useState<Record<string, ThreadResponse>>({});
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      if (objects.length === 0) return;
      try {
        const loaded = await Promise.all(objects.map((object) => api.thread(object.id, signal)));
        setThreads(Object.fromEntries(loaded.map((thread) => [thread.object.id, thread])));
        setError(null);
      } catch (loadError) {
        if (!(loadError instanceof DOMException && loadError.name === "AbortError")) {
          setError(loadError instanceof Error ? loadError.message : "Could not load notes.");
        }
      }
    },
    [objects],
  );

  usePolling(reload, 2000, objects.length > 0);
  useLiveUpdates(() => void reload());

  return { threads, error, reload };
}
