export interface Profile {
  id: string;
  display_name: string;
  initials: string;
  color: string;
  // Demo-only portrait; real profiles fall back to initials.
  photo?: string;
}

export interface ObjectSummary {
  marker_id?: number;
  id: string;
  identity_key: string;
  identity_kind: string;
  title: string;
  description: string | null;
}

export interface LiveEnrollment extends ObjectSummary {
  captured_views: string[];
  diagnostics: {
    frames_sampled: number;
    views_selected: number;
    views_enrolled: number;
    best_sharpness: number;
  };
}

export interface LiveScan {
  scan_id: string;
  captured_views: string[];
  diagnostics: LiveEnrollment["diagnostics"];
}

export interface AddViewsResult {
  object_id: string;
  reference_count: number;
  diagnostics: LiveEnrollment["diagnostics"];
}

export interface Post {
  id: number;
  object_id: string;
  author: Profile;
  body: string;
  created_at: string;
  parent_post_id: number | null;
  replies: Post[];
}

export interface ThreadResponse {
  object: ObjectSummary;
  posts: Post[];
  updated_at: string | null;
}

export interface Detection {
  identity_key: string;
  confidence: number;
  method: string;
  tier: "high" | "provisional";
  corners: [number, number][];
  center: [number, number];
  object: ObjectSummary | null;
  preview: {
    author_name: string;
    body: string;
    reply_count: number;
  } | null;
}

export interface RecognitionResponse {
  status: "starting" | "ready" | "unavailable" | "disabled";
  source: "camera" | "fixture" | "disabled";
  message: string | null;
  captured_at: string | null;
  frame_width: number;
  frame_height: number;
  detections: Detection[];
}

export interface HealthResponse {
  status: "ok";
  camera_status: string;
  camera_source: string;
  transcription_status: string;
  camera_index: number;
  llm_parser_enabled?: boolean;
  assistant_status: string;
  assistant_model: string;
  assistant_message: string | null;
}

export interface LockedTarget {
  object: ObjectSummary;
  parentPost: Post | null;
}

export interface AssistantMessage { role: "user" | "assistant"; content: string; }
export interface AssistantResponse { text: string; model: string; camera_used: boolean; camera_source: string; captured_at: string | null; awaiting_description: boolean; pending_edit_ids: number[]; pending_edit_body: string; read_aloud: boolean; awaiting_note: boolean; awaiting_name: boolean; pending_title: string; pending_body: string; pending_delete_ids: number[]; deletion_id: string | null; deleted_note_ids: number[]; memory_changed: boolean; saved_note: Post | null; saved_object: ObjectSummary | null; }
