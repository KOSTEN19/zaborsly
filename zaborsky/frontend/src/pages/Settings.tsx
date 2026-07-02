import { useEffect, useState } from "react";
import { api, SettingsData } from "../api/client";

export default function Settings() {
  const [data, setData] = useState<SettingsData | null>(null);

  useEffect(() => {
    api.settings().then(setData);
  }, []);

  if (!data) return <span className="loading loading-lg mx-auto block mt-20" />;

  const rows: [string, string][] = [
    ["Режим", data.single_camera_mode ? "1 камера" : "2 камеры"],
    ["Камера", data.camera_1_name],
    ["RTSP", data.camera_1_rtsp],
  ];

  if (data.single_camera_mode) {
    rows.push([
      "Въезд / выезд",
      "Авто: нет открытой сессии → въезд, есть на территории → выезд",
    ]);
  } else {
    rows.push(
      ["Камера 2", data.camera_2_name],
      ["RTSP камера 2", data.camera_2_rtsp],
      ["Cam1→Cam2 =", data.cam1_to_cam2_direction === "entry" ? "Въезд" : "Выезд"],
    );
  }

  rows.push(
    ["— Качество —", ""],
    ["Мин. уверенность (кадр)", String(data.min_confidence)],
    ["Мин. уверенность (подтвержд.)", String(data.min_confirmed_confidence)],
    ["Голосование", `${data.plate_vote_required} из ${data.plate_vote_window} кадров`],
    ["CLAHE (контраст)", data.enable_clahe ? "Вкл" : "Выкл"],
    ["ANPR разрешение", `${data.anpr_max_frame_width}px`],
    ["— Производительность —", ""],
    ["Live интервал (мс)", String(data.live_preview_interval_ms)],
    ["Live разрешение", `${data.live_max_frame_width}px`],
    ["ANPR интервал (мс)", String(data.anpr_min_interval_ms)],
    ["Порог движения", String(data.motion_min_area_ratio)],
    ["Потоки PyTorch", String(data.torch_num_threads)],
    ["Cooldown (сек)", String(data.detection_cooldown_sec)],
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Настройки</h1>
      <p className="text-base-content/60">
        Настройки задаются через файл <code className="bg-base-300 px-1 rounded">.env</code> на сервере.
      </p>

      <div className="card bg-base-100 shadow">
        <div className="card-body">
          <table className="table">
            <tbody>
              {rows.map(([key, val]) => (
                <tr key={key} className={!val ? "opacity-60" : ""}>
                  <td className="font-medium w-1/3">{key}</td>
                  <td className="font-mono text-sm break-all">{val || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
