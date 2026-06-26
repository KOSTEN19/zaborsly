import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { clearToken } from "../api/client";

const links = [
  { to: "/", label: "Дашборд" },
  { to: "/cameras", label: "Камеры" },
  { to: "/sessions", label: "Журнал" },
  { to: "/detections", label: "Детекции" },
  { to: "/settings", label: "Настройки" },
];

export default function Layout() {
  const navigate = useNavigate();

  const logout = () => {
    clearToken();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-base-200">
      <div className="navbar bg-base-100 shadow-lg px-4">
        <div className="flex-1">
          <Link to="/" className="btn btn-ghost text-xl font-bold">
            Zaborsky ANPR
          </Link>
        </div>
        <div className="flex-none gap-2 hidden md:flex">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) =>
                `btn btn-ghost btn-sm ${isActive ? "btn-active" : ""}`
              }
            >
              {l.label}
            </NavLink>
          ))}
          <button className="btn btn-outline btn-sm" onClick={logout}>
            Выйти
          </button>
        </div>
      </div>

      <div className="container mx-auto p-4 md:p-6 max-w-7xl">
        <Outlet />
      </div>
    </div>
  );
}
