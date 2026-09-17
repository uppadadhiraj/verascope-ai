import { type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  LayoutDashboard,
  FolderGit2,
  MessageSquare,
  Bug,
  ShieldAlert,
  History,
  LogOut,
  FolderTree,
  Network,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";

function NavLink({ to, icon, label, active }: { to: string; icon: ReactNode; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
        active ? "bg-indigo-600/20 text-indigo-300" : "text-slate-400 hover:bg-surface-border hover:text-slate-100"
      }`}
    >
      {icon}
      {label}
    </Link>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const { repositoryId } = useParams();

  const repoNav = repositoryId
    ? [
        { to: `/repositories/${repositoryId}`, icon: <FolderGit2 size={16} />, label: "Overview" },
        { to: `/repositories/${repositoryId}/explorer`, icon: <FolderTree size={16} />, label: "Explorer" },
        { to: `/repositories/${repositoryId}/graph`, icon: <Network size={16} />, label: "Dependency Graph" },
        { to: `/repositories/${repositoryId}/chat`, icon: <MessageSquare size={16} />, label: "Chat" },
        { to: `/repositories/${repositoryId}/debug`, icon: <Bug size={16} />, label: "Debugging" },
        { to: `/repositories/${repositoryId}/security`, icon: <ShieldAlert size={16} />, label: "Security" },
        { to: `/repositories/${repositoryId}/agents`, icon: <History size={16} />, label: "Agent History" },
      ]
    : [];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface">
      <aside className="flex w-56 flex-shrink-0 flex-col border-r border-surface-border bg-surface-raised">
        <div className="flex items-center gap-2 border-b border-surface-border px-4 py-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold">
            V
          </div>
          <span className="text-sm font-semibold tracking-tight">Verascope</span>
        </div>

        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
          <NavLink
            to="/dashboard"
            icon={<LayoutDashboard size={16} />}
            label="Dashboard"
            active={location.pathname === "/dashboard"}
          />
          {repoNav.length > 0 && (
            <>
              <div className="mt-4 mb-1 px-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Repository
              </div>
              {repoNav.map((item) => (
                <NavLink key={item.to} {...item} active={location.pathname === item.to} />
              ))}
            </>
          )}
        </nav>

        <div className="border-t border-surface-border p-3">
          <div className="mb-2 truncate px-2 text-xs text-slate-500">{user?.email}</div>
          <button onClick={logout} className="btn-secondary w-full">
            <LogOut size={14} />
            Log out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
