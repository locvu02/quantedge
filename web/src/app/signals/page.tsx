"use client";

import { useEffect, useState } from "react";

const fmt = (n: number | undefined, decimals = 1) =>
  n != null ? n.toFixed(decimals) : "-";

export default function SignalsPage() {
  const [signals, setSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tf, setTf] = useState("1h");

  useEffect(() => {
    setLoading(true);
    fetch(`/api/signals/scan?timeframe=${tf}`)
      .then(r => r.json())
      .then(d => setSignals(d.results || []))
      .finally(() => setLoading(false));
  }, [tf]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Signal Scanner</h1>
        <select value={tf} onChange={e => setTf(e.target.value)}
          className="bg-[var(--card)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm">
          <option value="1h">1 Hour</option>
          <option value="4h">4 Hours</option>
          <option value="1d">1 Day</option>
        </select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {signals.map((r: any, i: number) => (
          <div key={i} className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-lg">{r.symbol}</h3>
              {r.signal ? (
                <span className={`text-xs font-bold uppercase px-2 py-1 rounded ${
                  r.signal.direction === "long"
                    ? "bg-green-500/10 text-[var(--green)]"
                    : "bg-red-500/10 text-[var(--red)]"
                }`}>
                  {r.signal.direction}
                </span>
              ) : (
                <span className="text-xs text-[var(--muted)]">No signal</span>
              )}
            </div>
            {r.signal && (
              <div className="space-y-2 text-sm">
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-[var(--muted)]">Entry:</span> ${r.signal.entry_price?.toFixed(2)}</div>
                  <div><span className="text-[var(--muted)]">Confidence:</span> {(r.signal.confidence * 100).toFixed(0)}%</div>
                  <div><span className="text-[var(--muted)]">Stop Loss:</span> ${r.signal.stop_loss?.toFixed(2)}</div>
                  <div><span className="text-[var(--muted)]">Take Profit:</span> ${r.signal.take_profit?.toFixed(2)}</div>
                  <div><span className="text-[var(--muted)]">Risk:Reward:</span> 1:{r.signal.risk_reward?.toFixed(1)}</div>
                </div>
                <div className="mt-2 pt-2 border-t border-[var(--border)]">
                  <p className="text-xs text-[var(--muted)]">
                    Strategies: {r.signal.strategies?.join(", ")}
                  </p>
                  <p className="text-xs text-[var(--muted)] mt-1">
                    {r.signal.reasons?.join(" | ")}
                  </p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
