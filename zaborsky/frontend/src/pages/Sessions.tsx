import { useEffect, useState } from "react";
import { api, SessionsItem } from "../api/client";
import PhotoModal from "../components/PhotoModal";

const statusLabels: Record<string, string> = {
  on_site: "На территории",
  completed: "Выехал",
  unknown: "Неизвестно",
};

const statusBadges: Record<string, string> = {
  on_site: "badge-warning",
  completed: "badge-success",
  unknown: "badge-ghost",
};

export default function Sessions() {
  const [items, setItems] = useState<SessionsItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [plate, setPlate] = useState("");
  const [status, setStatus] = useState("");
  const [photo, setPhoto] = useState<{ url: string; title: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (plate) params.set("plate", plate);
    if (status) params.set("status", status);
    api
      .sessions(params)
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [page, status]);

  const search = () => {
    setPage(1);
    load();
  };

  const pages = Math.ceil(total / 20) || 1;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Журнал заездов / выездов</h1>

      <div className="flex flex-wrap gap-2">
        <input
          className="input input-bordered input-sm"
          placeholder="Номер"
          value={plate}
          onChange={(e) => setPlate(e.target.value.toUpperCase())}
        />
        <select
          className="select select-bordered select-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Все статусы</option>
          <option value="on_site">На территории</option>
          <option value="completed">Выехал</option>
          <option value="unknown">Неизвестно</option>
        </select>
        <button className="btn btn-primary btn-sm" onClick={search}>
          Найти
        </button>
      </div>

      <div className="card bg-base-100 shadow overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th>Номер</th>
              <th>Въезд</th>
              <th>Выезд</th>
              <th>Статус</th>
              <th>Фото</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="text-center py-8">
                  <span className="loading loading-spinner" />
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-base-content/50">
                  Записей нет
                </td>
              </tr>
            ) : (
              items.map((s) => (
                <tr key={s.id}>
                  <td className="font-mono font-bold">{s.plate}</td>
                  <td>{s.entry_at ? new Date(s.entry_at).toLocaleString("ru-RU") : "—"}</td>
                  <td>{s.exit_at ? new Date(s.exit_at).toLocaleString("ru-RU") : "—"}</td>
                  <td>
                    <span className={`badge ${statusBadges[s.status] || ""}`}>
                      {statusLabels[s.status] || s.status}
                    </span>
                  </td>
                  <td className="space-x-1">
                    {s.entry_photo_url && (
                      <button
                        className="btn btn-xs btn-outline"
                        onClick={() =>
                          setPhoto({ url: s.entry_photo_url!, title: `Въезд ${s.plate}` })
                        }
                      >
                        Въезд
                      </button>
                    )}
                    {s.exit_photo_url && (
                      <button
                        className="btn btn-xs btn-outline"
                        onClick={() =>
                          setPhoto({ url: s.exit_photo_url!, title: `Выезд ${s.plate}` })
                        }
                      >
                        Выезд
                      </button>
                    )}
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
