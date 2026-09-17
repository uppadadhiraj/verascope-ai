import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { authApi } from "@/api/endpoints";
import type { User } from "@/api/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("verascope_token");
    const cachedUser = localStorage.getItem("verascope_user");
    if (token && cachedUser) {
      setUser(JSON.parse(cachedUser));
    }
    setLoading(false);
  }, []);

  function persist(token: string, u: User) {
    localStorage.setItem("verascope_token", token);
    localStorage.setItem("verascope_user", JSON.stringify(u));
    setUser(u);
  }

  async function login(email: string, password: string) {
    const result = await authApi.login(email, password);
    persist(result.access_token, result.user);
  }

  async function register(email: string, password: string, fullName?: string) {
    const result = await authApi.register(email, password, fullName);
    persist(result.access_token, result.user);
  }

  function logout() {
    localStorage.removeItem("verascope_token");
    localStorage.removeItem("verascope_user");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
