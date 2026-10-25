export interface Profile {
  id: string;
  display_name: string;
  initials: string;
  color: string;
  // Demo-only portrait; real profiles fall back to initials.
  photo?: string;
}

export interface ObjectSummary {
  id: string;
  marker_id: number;
  title: string;
  description: string | null;
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
  marker_id: number;
  corners: [number, number][];
  center: [number, number];
  object: ObjectSummary | null;
  preview: {
    author_name: string;
    body: string;
    reply_count: number;
  } | null;
}

export interface ObjectDetection {
  label: string;
  confidence: number;
  box: [number, number, number, number];
}

export interface RecognitionResponse {
  status: "starting" | "ready" | "unavailable" | "disabled";
  source: "camera" | "fixture" | "disabled";
  message: string | null;
  captured_at: string | null;
  frame_width: number;
  frame_height: number;
  detections: Detection[];
  objects: ObjectDetection[];
  object_detection_status: "loading" | "ready" | "unavailable" | "disabled";
  object_detection_message: string | null;
}

export interface HealthResponse {
  status: "ok";
  camera_status: string;
  camera_source: string;
  object_detection_status: string;
  transcription_status: string;
}

export interface LockedTarget {
  object: ObjectSummary;
  parentPost: Post | null;
}
