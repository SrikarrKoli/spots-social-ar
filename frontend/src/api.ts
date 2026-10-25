import type {
  AddViewsResult,
  AssistantMessage,
  AssistantResponse,
  HealthResponse,
  LiveEnrollment,
  LiveScan,
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
  askAssistant(message: string, history: AssistantMessage[], objectId: string | null, includeCamera: boolean, signal?: AbortSignal, note?: { authorId: string; requestId: string; awaitingNote: boolean; awaitingName?: boolean; pendingTitle?: string; pendingBody?: string; pendingDeleteIds?: number[]; lastNoteId?: number; deletionId?: string; awaitingDescription?: boolean; pendingEditIds?: number[]; pendingEditBody?: string }) {
    return fetch("/api/assistant", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: history.slice(-12).map((item) => ({ ...item, content: item.content.slice(0, 4000) })), object_id: objectId, include_camera: includeCamera, author_id: note?.authorId ?? "guest", request_id: note?.requestId, awaiting_note: note?.awaitingNote ?? false, awaiting_name: note?.awaitingName ?? false, pending_title: note?.pendingTitle ?? "", pending_body: note?.pendingBody ?? "", pending_delete_ids: note?.pendingDeleteIds ?? [], last_note_id: note?.lastNoteId, deletion_id: note?.deletionId, awaiting_description: note?.awaitingDescription ?? false, pending_edit_ids: note?.pendingEditIds ?? [], pending_edit_body: note?.pendingEditBody ?? "" }), signal,
    }).then((response) => parseResponse<AssistantResponse>(response));
  },
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
  enrollObject(title: string, description: string, image: File) {
    const form = new FormData();
    form.append("title", title);
    if (description) form.append("description", description);
    form.append("image", image);
    return fetch("/api/objects/enroll", { method: "POST", body: form }).then(
      (response) => parseResponse<ObjectSummary>(response),
    );
  },
  scanLive() {
    return fetch("/api/objects/enroll-live/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_seconds: 4 }),
    }).then((response) => parseResponse<LiveScan>(response));
  },
  scanMore(scanId: string) {
    return fetch(`/api/objects/enroll-live/scans/${encodeURIComponent(scanId)}/more`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_seconds: 4 }),
    }).then((response) => parseResponse<LiveScan>(response));
  },
  discardScan(scanId: string) {
    return fetch(`/api/objects/enroll-live/scans/${encodeURIComponent(scanId)}`, {
      method: "DELETE",
    }).then((response) => parseResponse<{ deleted: boolean }>(response));
  },
  enrollLive(scanId: string, title: string, description: string) {
    return fetch("/api/objects/enroll-live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scan_id: scanId,
        title,
        description: description || null,
      }),
    }).then((response) => parseResponse<LiveEnrollment>(response));
  },
  addViews(objectId: string) {
    return fetch(`/api/objects/${encodeURIComponent(objectId)}/add-views`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_seconds: 4 }),
    }).then((response) => parseResponse<AddViewsResult>(response));
  },
  discardObject(objectId: string) {
    return fetch(`/api/objects/${encodeURIComponent(objectId)}`, {
      method: "DELETE",
    }).then((response) => parseResponse<{ deleted: boolean }>(response));
  },
  confirmIdentity(identityKey: string) {
    return fetch("/api/recognition/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity_key: identityKey }),
    }).then((response) => parseResponse<{ confirmed: boolean }>(response));
  },
  transcribe(blob: Blob, signal?: AbortSignal) {
    const form = new FormData();
    const extension = blob.type.includes("mp4") ? "mp4" : blob.type.includes("wav") ? "wav" : "webm";
    form.append("audio", blob, `recording.${extension}`);
    return fetch("/api/transcriptions", {
      method: "POST",
      body: form,
      signal,
    }).then((response) =>
      parseResponse<{ text: string; provider: string }>(response),
    );
  },
};
