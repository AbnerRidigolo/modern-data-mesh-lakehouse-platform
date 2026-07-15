import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import CatalogPage from "./pages/CatalogPage";
import DashboardPage from "./pages/DashboardPage";
import DataQualityPage from "./pages/DataQualityPage";
import LoginPage from "./pages/LoginPage";
import MLOpsPage from "./pages/MLOpsPage";
import SearchPage from "./pages/SearchPage";
import TimeTravelPage from "./pages/TimeTravelPage";

function ProtectedLayout() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <Layout />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/time-travel" element={<TimeTravelPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/mlops" element={<MLOpsPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/data-quality" element={<DataQualityPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
