import { useEffect, useState } from "react";
import { api, CameraItem, CameraLiveStatus, getToken } from "../api/client";

interface CameraFeedProps {
  camera: CameraItem;
}

function useLiveSnapshot(cameraId: number, enabled: boolean) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;

    let objectUrl: string | null = null;
    const token = getToken();

    const load = () => {
      fetch(`/api/cameras/${cameraId}/snapshot?t=${Date.now()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((r) => {
          if (!r.ok) throw new Error("snapshot failed");
          return r.blob();
        })
        .then((blob) => {
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          objectUrl = URL.createObjectURL(blob);
          setSrc(objectUrl);
        })
        .catch(() => setSrc(null));
    };

    load();
    const interval = setInterval(load, 500);
    return () => {
      clearInterval(interval);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [cameraId, enabled]);

  return src;
}

export default function CameraFeed({ camera }: CameraFeedProps) {
  const [live, setLive] = useState<CameraLiveStatus | null>(null);
  const snapshot = useLiveSnapshot(camera.id, true);

  useEffect(() => {
    const load = () => {
      api.cameraLive(camera.id).then(setLive).catch(() => {});
    };
    load();
    const interval = setInterval(load, 500);
    return () => clearInterval(interval);
  }, [camera.id]);

  const isOnline = live?.online ?? camera.is_online;
  const plate = live?.plate;
  const confidence = live?.confidence;

  return (
    <div className="card bg-base-100 shadow-xl">
      <div className="card-body p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="card-title text-lg">{camera.name}</h2>
          <span className={`badge ${isOnline ? "badge-success" : "badge-error"}`}>
            {isOnline ? "Online" : "Offline"}
          </span>
        </div>

        <div className="relative aspect-video bg-base-300 rounded-lg overflow-hidden">
          {snapshot ? (
            <img src={snapshot} alt={camera.name} className="w-full h-full object-contain" />
          ) : (
            <div className="flex items-center justify-center h-full min-h-[200px] text-base-content/50">
              {isOnline ? (
                <span className="loading loading-spinner loading-lg" />
              ) : (
                "Камера недоступна"
              )}
            </div>
          )}

          {plate && (
            <div className="absolute top-3 left-3 flex flex-col gap-1">
              <div className="bg-black/75 text-white px-4 py-2 rounded-lg shadow-lg border border-primary/50">
                <span className="font-mono text-2xl font-bold tracking-wider">{plate}</span>
              </div>
              {confidence != null && (
                <span className="bg-black/60 text-white text-xs px-2 py-1 rounded w-fit">
                  {Math.round(confidence * 100)}% уверенность
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
