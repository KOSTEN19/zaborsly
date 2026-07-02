import { useEffect, useState } from "react";
import { api, DashboardStats } from "../api/client";

function StatCard({ title, value, color }: { title: string; value: number; color: string }) {
  return (
    <div className={`stat bg-base-100 rounded-box shadow ${color}`}>
      <div className="stat-title">{title}</div>
      <div className="stat-value text-3xl">{value}</div>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setError(e.message));
    const interval = setInterval(() => {
      api.dashboard().then(setData).catch(() => {});
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <div className="alert alert-error">{error}</div>;
  if (!data) return <span className="loading loading-lg mx-auto block mt-20" />;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Дашборд</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Въезды сегодня" value={data.entries_today} color="" />
        <StatCard title="Выезды сегодня" value={data.exits_today} color="" />
        <StatCard title="На территории" value={data.on_site} color="" />
        <StatCard title="Детекций сегодня" value={data.detections_today} color="" />
      </div>

      <div className="card bg-base-100 shadow">
        <div className="card-body">
          <h2 className="card-title">Статус камер</h2>
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Камера</th>
                  <th>Статус</th>
                  <th>Последняя активность</th>
                </tr>
              </thead>
              <tbody>
                {data.cameras.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td>
                      <span className={`badge ${c.is_online ? "badge-success" : "badge-error"}`}>
                        {c.is_online ? "Online" : "Offline"}
                      </span>
                    </td>
                    <td>
                      {c.last_seen_at
                        ? new Date(c.last_seen_at).toLocaleString("ru-RU")
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
