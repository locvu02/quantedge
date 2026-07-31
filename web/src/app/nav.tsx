"use client";

import { useAuth } from "@/lib/auth";

export function NavBar() {
  const { user, logout, loading } = useAuth();

  return (
    <nav className="border-b border-[var(--border)] bg-[var(--card)] px-6 py-4">
      <div className="mx-auto flex max-w-7xl items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">
          <span className="text-[var(--accent)]">Quant</span>Edge
        </h1>
        <div className="flex gap-4 text-sm text-[var(--muted)] items-center">
          <a href="/" className="hover:text-[var(--text)] transition-colors">Dashboard</a>
          <a href="/signals" className="hover:text-[var(--text)] transition-colors">Signals</a>
          <a href="/backtest" className="hover:text-[var(--text)] transition-colors">Backtest</a>

          {loading ? (
            <span className="w-6 h-6 rounded-full bg-[var(--border)] animate-pulse" />
          ) : user ? (
            <div className="flex items-center gap-3">
              <span className="text-[var(--accent)]">{user.username}</span>
              <button
                onClick={logout}
                className="px-3 py-1 rounded bg-[var(--border)] hover:bg-[var(--muted)]/20 transition-colors text-xs"
              >
                Logout
              </button>
            </div>
          ) : (
            <a href="/login" className="px-3 py-1 rounded bg-[var(--accent)] text-white hover:opacity-90 transition-colors text-xs">
              Login
            </a>
          )}
        </div>
      </div>
    </nav>
  );
}
