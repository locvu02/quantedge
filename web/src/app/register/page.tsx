"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(email, username, password);
      router.push("/");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold mb-6">
          Create <span className="text-[var(--accent)]">Quant</span>Edge Account
        </h1>

        {error && (
          <div className="bg-[var(--red)]/10 border border-[var(--red)]/30 rounded-lg p-3 mb-4 text-sm text-[var(--red)]">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-[var(--muted)] mb-1">Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-[var(--accent)]" required />
          </div>
          <div>
            <label className="block text-sm text-[var(--muted)] mb-1">Username</label>
            <input type="text" value={username} onChange={e => setUsername(e.target.value)}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-[var(--accent)]" required />
          </div>
          <div>
            <label className="block text-sm text-[var(--muted)] mb-1">Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-[var(--accent)]" required />
          </div>
          <button type="submit" disabled={loading}
            className="w-full bg-[var(--accent)] text-white rounded-lg py-3 font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
            {loading ? "Creating..." : "Create Account"}
          </button>
        </form>

        <p className="text-sm text-[var(--muted)] mt-4 text-center">
          Already have an account?{" "}
          <a href="/login" className="text-[var(--accent)] hover:underline">Sign In</a>
        </p>
      </div>
    </div>
  );
}
