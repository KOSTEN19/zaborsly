import { useEffect, useState } from "react";
import { api, DetectionItem } from "../api/client";
import PhotoModal from "../components/PhotoModal";

const directionLabels: Record<string, string> = {
  entry: "Въезд",
  exit: "Выезд",
  unknown: "—",
};

export default function Detections() {
  const [items, setItems] = useState<DetectionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [plate, setPlate] = useState("");
  const [photo, setPhoto] = useState<{ url: string; title: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (plate) params.set("plate", plate);
    api
      .detections(params)
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [page]);

  const pages = Math.ceil(total / 20) || 1;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Сырые детекции</h1>

      <div className="flex gap-2">
        <input
          className="input input-bordered input-sm"
          placeholder="Номер"
          value={plate}
          onChange={(e) => setPlate(e.target.value.toUpperCase())}
        />
        <button
          className="btn btn-primary btn-sm"
          onClick={() => {
            setPage(1);
            load();
          }}
        >
          Найти
        </button>
      </div>

      <div className="card bg-base-100 shadow overflow-x-auto">
        <table className="table table-sm">
          <thead>
            <tr>
              <th>Время</th>
              <th>Камера</th>
              <th>Номер</th>
              <th>Уверенность</th>
              <th>Направление</th>
              <th>Фото</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="text-center py-8">
                  <span className="loading loading-spinner" />
                </td>
              </tr>
            ) : (
              items.map((d) => (
                <tr key={d.id}>
                  <td>{new Date(d.detected_at).toLocaleString("ru-RU")}</td>
                  <td>{d.camera_name || `Cam ${d.camera_id}`}</td>
                  <td className="font-mono font-bold">{d.plate}</td>
                  <td>{(d.confidence * 100).toFixed(0)}%</td>
                  <td>{directionLabels[d.direction] || d.direction}</td>
                  <td>
                    <button
                      className="btn btn-xs btn-outline"
                      onClick={() =>
                        setPhoto({ url: d.photo_url, title: `${d.plate} — ${d.camera_name}` })
                      }
                    >
                      Открыть
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="join">
        <button className="join-item btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          «
        </button>
        <button className="join-item btn btn-sm btn-disabled">
          {page} / {pages}
        </button>
        <button
          className="join-item btn btn-sm"
          disabled={page >= pages}
          onClick={() => setPage(page + 1)}
        >
          »
        </button>
      </div>

      {photo && (
        <PhotoModal url={photo.url} title={photo.title} onClose={() => setPhoto(null)} />
      )}
    </div>
  );
}
