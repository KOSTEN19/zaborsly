import { useEffect, useState } from "react";
import { api, CameraItem } from "../api/client";
import CameraFeed from "../components/CameraFeed";

export default function Cameras() {
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      api.cameras().then(setCameras).finally(() => setLoading(false));
    };
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <span className="loading loading-lg mx-auto block mt-20" />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Просмотр камер</h1>
        <p className="text-base-content/60 mt-1">
          Live-кадры с распознанным номером в левом верхнем углу
        </p>
      </div>

      {cameras.length === 0 ? (
        <div className="alert">Камеры не настроены</div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {cameras.map((camera) => (
            <CameraFeed key={camera.id} camera={camera} />
          ))}
        </div>
      )}
    </div>
  );
}
