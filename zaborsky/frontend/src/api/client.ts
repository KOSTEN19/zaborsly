const TOKEN_KEY = "zaborsky_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const res = await fetch(`/api${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  login: async (username: string, password: string) => {
    const body = new URLSearchParams({ username, password });
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) throw new Error("Неверный логин или пароль");
    return res.json() as Promise<{ access_token: string }>;
  },
  dashboard: () => request<DashboardStats>("/dashboard"),
  sessions: (params: URLSearchParams) =>
    request<Paginated<SessionsItem>>(`/sessions?${params}`),
  detections: (params: URLSearchParams) =>
    request<Paginated<DetectionItem>>(`/detections?${params}`),
  settings: () => request<SettingsData>("/settings"),
  cameras: () => request<CameraItem[]>("/cameras"),
  cameraLive: (cameraId: number) => request<CameraLiveStatus>(`/cameras/${cameraId}/live`),
};

export interface DashboardStats {
  entries_today: number;
  exits_today: number;
  on_site: number;
  detections_today: number;
  cameras: CameraItem[];
}

export interface CameraItem {
  id: number;
  name: string;
  is_online: boolean;
  last_seen_at: string | null;
}

export interface CameraLiveStatus {
  camera_id: number;
  camera_name: string;
  plate: string | null;
  confidence: number | null;
  detected_at: string | null;
  online: boolean;
}

export interface SessionsItem {
  id: number;
  plate: string;
  entry_at: string | null;
  exit_at: string | null;
  entry_photo_url: string | null;
  exit_photo_url: string | null;
  status: string;
}

export interface DetectionItem {
  id: number;
  camera_id: number;
  camera_name: string | null;
  plate: string;
  confidence: number;
  direction: string;
  detected_at: string;
  photo_url: string;
}

export interface SettingsData {
  camera_1_name: string;
  camera_2_name: string;
  camera_1_rtsp: string;
  camera_2_rtsp: string;
  cam1_to_cam2_direction: string;
  movement_window_sec: number;
  detection_cooldown_sec: number;
  min_confidence: number;
  min_confirmed_confidence: number;
  live_preview_interval_ms: number;
  live_max_frame_width: number;
  anpr_max_frame_width: number;
  anpr_min_interval_ms: number;
  enable_clahe: boolean;
  motion_min_area_ratio: number;
  plate_vote_required: number;
  plate_vote_window: number;
  torch_num_threads: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
