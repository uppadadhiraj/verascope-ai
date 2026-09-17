import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RepositoryPage } from "@/pages/RepositoryPage";
import { ExplorerPage } from "@/pages/ExplorerPage";
import { DependencyGraphPage } from "@/pages/DependencyGraphPage";
import { ChatPage } from "@/pages/ChatPage";
import { DebugPage } from "@/pages/DebugPage";
import { TaskDetailPage } from "@/pages/TaskDetailPage";
import { SecurityPage } from "@/pages/SecurityPage";
import { AgentHistoryPage } from "@/pages/AgentHistoryPage";

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      <Route path="/repositories/:repositoryId" element={<ProtectedRoute><RepositoryPage /></ProtectedRoute>} />
      <Route path="/repositories/:repositoryId/explorer" element={<ProtectedRoute><ExplorerPage /></ProtectedRoute>} />
      <Route path="/repositories/:repositoryId/graph" element={<ProtectedRoute><DependencyGraphPage /></ProtectedRoute>} />
      <Route path="/repositories/:repositoryId/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
      <Route path="/repositories/:repositoryId/debug" element={<ProtectedRoute><DebugPage /></ProtectedRoute>} />
      <Route
        path="/repositories/:repositoryId/debug/:taskId"
        element={<ProtectedRoute><TaskDetailPage /></ProtectedRoute>}
      />
      <Route path="/repositories/:repositoryId/security" element={<ProtectedRoute><SecurityPage /></ProtectedRoute>} />
      <Route path="/repositories/:repositoryId/agents" element={<ProtectedRoute><AgentHistoryPage /></ProtectedRoute>} />

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
