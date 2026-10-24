import type {
  HealthResponse,
  ObjectSummary,
  Post,
  Profile,
  RecognitionResponse,
  ThreadResponse,
} from "./types";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // The HTTP status remains useful when a proxy returns non-JSON.
    }
    throw new ApiRequestError(message, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health(signal?: AbortSignal) {
    return fetch("/api/health", { signal }).then((response) =>
      parseResponse<HealthResponse>(response),
    );
  },
  profiles(signal?: AbortSignal) {
    return fetch("/api/profiles", { signal }).then((response) =>
      parseResponse<Profile[]>(response),
    );
  },
  objects(signal?: AbortSignal) {
    return fetch("/api/objects", { signal }).then((response) =>
      parseResponse<ObjectSummary[]>(response),
    );
  },
  recognition(signal?: AbortSignal) {
    return fetch("/api/recognition", {
      signal,
      cache: "no-store",
    }).then((response) => parseResponse<RecognitionResponse>(response));
  },
  thread(objectId: string, signal?: AbortSignal) {
    return fetch(`/api/objects/${encodeURIComponent(objectId)}/posts`, {
      signal,
      cache: "no-store",
    }).then((response) => parseResponse<ThreadResponse>(response));
  },
  createPost(
    objectId: string,
    body: {
      author_id: string;
      body: string;
      parent_post_id: number | null;
      client_request_id: string;
    },
  ) {
    return fetch(`/api/objects/${encodeURIComponent(objectId)}/posts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((response) => parseResponse<Post>(response));
  },
  transcribe(blob: Blob) {
    const form = new FormData();
    const extension = blob.type.includes("wav") ? "wav" : "webm";
    form.append("audio", blob, `recording.${extension}`);
    return fetch("/api/transcriptions", {
      method: "POST",
      body: form,
    }).then((response) =>
      parseResponse<{ text: string; provider: string }>(response),
    );
  },
};
