import { useEffect, useRef } from "react";

interface LiveUpdate {
  type: "post.created";
  object_id: string;
  post_id: number;
  author_id: string;
}

export function useLiveUpdates(onUpdate: (update: LiveUpdate) => void) {
  const callbackRef = useRef(onUpdate);
  callbackRef.current = onUpdate;

  useEffect(() => {
    const events = new EventSource("/api/events");
    const handleUpdate = (event: MessageEvent<string>) => {
      callbackRef.current(JSON.parse(event.data) as LiveUpdate);
    };
    events.addEventListener("update", handleUpdate as EventListener);
    return () => events.close();
  }, []);
}
