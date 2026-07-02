import { FormEvent, useEffect, useState } from "react";
import { api, SettingsData } from "../api/client";

type FormState = Omit<SettingsData, "single_camera_mode">;

export default function Settings() {
  const [form, setForm] = useState<FormState | null>(null);
  const [singleCamera, setSingleCamera] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [checkPassword, setCheckPassword] = useState("");
  const [checkResult, setCheckResult] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changingPw, setChangingPw] = useState(false);

  useEffect(() => {
    api.settings().then((data) => {
      setSingleCamera(data.single_camera_mode);
      const { single_camera_mode: _, ...rest } = data;
      setForm(rest);
    });
  }, []);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const updated = await api.updateSettings(form);
      setSingleCamera(updated.single_camera_mode);
      const { single_camera_mode: _, ...rest } = updated;
      setForm(rest);
      setMessage(
        "Настройки сохранены. ANPR-параметры worker подхватит за ~30 сек. " +
          "При смене RTSP выполните: docker compose restart worker"
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const verifyPassword = async () => {
    setChecking(true);
    setCheckResult(null);
    try {
      const res = await api.verifyPassword(checkPassword);
      setCheckResult(res.valid ? "Пароль верный ✓" : "Пароль неверный ✗");
    } catch {
      setCheckResult("Ошибка проверки");
    } finally {
      setChecking(false);
    }
  };

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setError("Новый пароль и подтверждение не совпадают");
      return;
    }
    setChangingPw(true);
    setError("");
    setMessage("");
    try {
      const res = await api.changePassword(currentPassword, newPassword);
      setMessage(res.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сменить пароль");
    } finally {
      setChangingPw(false);
    }
  };

  if (!form) return <span className="loading loading-lg mx-auto block mt-20" />;

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">Настройки</h1>

      {message && <div className="alert alert-success text-sm">{message}</div>}
      {error && <div className="alert alert-error text-sm">{error}</div>}

      <div className="card bg-base-100 shadow">
        <div className="card-body">
          <h2 className="card-title text-lg">Пароль администратора</h2>
          <div className="flex flex-wrap gap-2 items-end">
            <label className="form-control flex-1 min-w-[200px]">
              <span className="label-text">Проверить пароль</span>
              <input
                type="password"
                className="input input-bordered input-sm"
                value={checkPassword}
                onChange={(e) => setCheckPassword(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={checking || !checkPassword}
              onClick={verifyPassword}
            >
              {checking ? <span className="loading loading-spinner loading-xs" /> : "Проверить"}
            </button>
          </div>
          {checkResult && (
            <p className={`text-sm ${checkResult.includes("✓") ? "text-success" : "text-error"}`}>
              {checkResult}
            </p>
          )}

          <form onSubmit={changePassword} className="grid gap-3 mt-4 pt-4 border-t border-base-300">
            <label className="form-control">
              <span className="label-text">Текущий пароль</span>
              <input
                type="password"
                className="input input-bordered input-sm"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </label>
            <label className="form-control">
              <span className="label-text">Новый пароль</span>
              <input
                type="password"
                className="input input-bordered input-sm"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={6}
                required
              />
            </label>
            <label className="form-control">
              <span className="label-text">Подтверждение</span>
              <input
                type="password"
                className="input input-bordered input-sm"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={6}
                required
              />
            </label>
            <button type="submit" className="btn btn-primary btn-sm w-fit" disabled={changingPw}>
              {changingPw ? <span className="loading loading-spinner loading-xs" /> : "Сменить пароль"}
            </button>
          </form>
        </div>
      </div>

      <form onSubmit={save} className="card bg-base-100 shadow">
        <div className="card-body gap-4">
          <h2 className="card-title text-lg">Камера</h2>
          <p className="text-sm text-base-content/60">
            Режим: {singleCamera ? "1 камера" : "2 камеры"}. Вторая камера включается, если заполнен RTSP камеры 2.
          </p>

          <label className="form-control">
            <span className="label-text">Название</span>
            <input
              className="input input-bordered input-sm"
              value={form.camera_1_name}
              onChange={(e) => set("camera_1_name", e.target.value)}
              required
            />
          </label>
          <label className="form-control">
            <span className="label-text">RTSP URL</span>
            <input
              className="input input-bordered input-sm font-mono text-xs"
              value={form.camera_1_rtsp}
              onChange={(e) => set("camera_1_rtsp", e.target.value)}
              placeholder="rtsp://user:pass@192.168.1.101:554/stream1"
            />
          </label>
          <label className="form-control">
            <span className="label-text">ROI (x,y,w,h)</span>
            <input
              className="input input-bordered input-sm font-mono text-xs"
              value={form.camera_1_roi}
              onChange={(e) => set("camera_1_roi", e.target.value)}
              placeholder="0.1,0.2,0.8,0.6"
            />
          </label>

          <h3 className="font-semibold pt-2">Камера 2 (опционально)</h3>
          <label className="form-control">
            <span className="label-text">Название</span>
            <input
              className="input input-bordered input-sm"
              value={form.camera_2_name}
              onChange={(e) => set("camera_2_name", e.target.value)}
            />
          </label>
          <label className="form-control">
            <span className="label-text">RTSP URL</span>
            <input
              className="input input-bordered input-sm font-mono text-xs"
              value={form.camera_2_rtsp}
              onChange={(e) => set("camera_2_rtsp", e.target.value)}
            />
          </label>

          {!singleCamera && (
            <label className="form-control">
              <span className="label-text">Cam1 → Cam2</span>
              <select
                className="select select-bordered select-sm"
                value={form.cam1_to_cam2_direction}
                onChange={(e) => set("cam1_to_cam2_direction", e.target.value)}
              >
                <option value="entry">Въезд</option>
                <option value="exit">Выезд</option>
              </select>
            </label>
          )}

          <h2 className="card-title text-lg pt-2">Распознавание</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="form-control">
              <span className="label-text">Мин. уверенность (кадр)</span>
              <input
                type="number"
                step="0.01"
                className="input input-bordered input-sm"
                value={form.min_confidence}
                onChange={(e) => set("min_confidence", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">Мин. уверенность (подтв.)</span>
              <input
                type="number"
                step="0.01"
                className="input input-bordered input-sm"
                value={form.min_confirmed_confidence}
                onChange={(e) => set("min_confirmed_confidence", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">Голосование (из)</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.plate_vote_window}
                onChange={(e) => set("plate_vote_window", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">Голосование (нужно)</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.plate_vote_required}
                onChange={(e) => set("plate_vote_required", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">Cooldown (сек)</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.detection_cooldown_sec}
                onChange={(e) => set("detection_cooldown_sec", Number(e.target.value))}
              />
            </label>
            <label className="form-control label cursor-pointer justify-start gap-3">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={form.enable_clahe}
                onChange={(e) => set("enable_clahe", e.target.checked)}
              />
              <span className="label-text">CLAHE (контраст)</span>
            </label>
          </div>

          <h2 className="card-title text-lg pt-2">Производительность</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="form-control">
              <span className="label-text">Live интервал (мс)</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.live_preview_interval_ms}
                onChange={(e) => set("live_preview_interval_ms", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">Live ширина (px)</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.live_max_frame_width}
                onChange={(e) => set("live_max_frame_width", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">ANPR ширина (px)</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.anpr_max_frame_width}
                onChange={(e) => set("anpr_max_frame_width", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">ANPR интервал (мс)</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.anpr_min_interval_ms}
                onChange={(e) => set("anpr_min_interval_ms", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">Порог движения</span>
              <input
                type="number"
                step="0.0001"
                className="input input-bordered input-sm"
                value={form.motion_min_area_ratio}
                onChange={(e) => set("motion_min_area_ratio", Number(e.target.value))}
              />
            </label>
            <label className="form-control">
              <span className="label-text">Потоки PyTorch</span>
              <input
                type="number"
                className="input input-bordered input-sm"
                value={form.torch_num_threads}
                onChange={(e) => set("torch_num_threads", Number(e.target.value))}
              />
            </label>
          </div>

          <button type="submit" className="btn btn-primary mt-2" disabled={saving}>
            {saving ? <span className="loading loading-spinner" /> : "Сохранить настройки"}
          </button>
        </div>
      </form>
    </div>
  );
}
