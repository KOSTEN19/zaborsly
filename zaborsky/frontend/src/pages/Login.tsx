import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api/client";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { access_token } = await api.login(username, password);
      setToken(access_token);
      navigate("/");
    } catch {
      setError("Неверный логин или пароль");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200 p-4">
      <div className="card w-full max-w-md bg-base-100 shadow-xl">
        <div className="card-body">
          <h1 className="card-title text-2xl justify-center mb-2">Zaborsky ANPR</h1>
          <p className="text-center text-base-content/60 mb-4">Вход в админ-панель</p>
          <form onSubmit={submit} className="space-y-4">
            <label className="form-control w-full">
              <span className="label-text">Логин</span>
              <input
                className="input input-bordered w-full"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label className="form-control w-full">
              <span className="label-text">Пароль</span>
              <input
                type="password"
                className="input input-bordered w-full"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            {error && <div className="alert alert-error text-sm">{error}</div>}
            <button className="btn btn-primary w-full" disabled={loading}>
              {loading ? <span className="loading loading-spinner" /> : "Войти"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
