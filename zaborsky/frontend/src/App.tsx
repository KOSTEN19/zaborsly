import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Cameras from "./pages/Cameras";
import Dashboard from "./pages/Dashboard";
import Detections from "./pages/Detections";
import Login from "./pages/Login";
import Sessions from "./pages/Sessions";
import Settings from "./pages/Settings";
import { getToken } from "./api/client";

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={getToken() ? <Navigate to="/" replace /> : <Login />}
      />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/cameras" element={<Cameras />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/detections" element={<Detections />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
