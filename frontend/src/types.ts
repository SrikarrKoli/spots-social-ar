export interface Profile {
  id: string;
  display_name: string;
  initials: string;
  color: string;
}

export interface ObjectSummary {
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
}

export interface LockedTarget {
  object: ObjectSummary;
  parentPost: Post | null;
}
