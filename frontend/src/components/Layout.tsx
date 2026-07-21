import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";
import { getHealth } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";

const NAV_ITEMS = [
  { to: "/", label: "📊 BI Dashboard & Cache", end: true },
  { to: "/time-travel", label: "🕰️ Delta Lake Time Travel" },
  { to: "/catalog", label: "🕸️ Catálogo Data Mesh" },
  { to: "/mlops", label: "📈 MLOps: Precificação" },
  { to: "/search", label: "🔍 Busca Semântica" },
  { to: "/copilot", label: "🤖 AI Copilot" },
  { to: "/data-quality", label: "✅ Data Quality" },
];

export default function Layout() {
  const { logout } = useAuth();
  const { data: health, isError } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 15000,
    retry: false,
  });

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>🕸️ Enterprise Data Mesh</h1>
          <p>Portal de Governança &amp; Lakehouse</p>
        </div>

        <ul className="nav-list">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="sidebar-status">
          <span className={`status-pill ${isError ? "error" : "ok"}`}>
            {isError ? "🔴 API Gateway: Offline" : "🟢 API Gateway: Ativo"}
          </span>
          {health && (
            <>
              <span>💾 DB: {health.database_connected ? "conectado" : "indisponível"}</span>
              <span>⚡ Cache: {health.cache_type}</span>
            </>
          )}
          <button type="button" className="btn secondary mt-16" onClick={logout}>
            Sair
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
