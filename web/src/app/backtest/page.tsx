"use client";

import { useEffect, useState, lazy, Suspense } from "react";

const Chart = lazy(() =>
  import("recharts").then(mod => {
    const { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } = mod;
    return {
      default: ({ data }: { data: any[] }) => (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data || []}>
            <CartesianGrid stroke="#1e1e2e" strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" tick={false} />
            <YAxis stroke="#64748b" fontSize={12} />
            <Tooltip contentStyle={{ background: "#12121a", border: "1px solid #1e1e2e", borderRadius: "8px", color: "#e2e8f0" }}
              formatter={(v: number) => [`$${v.toLocaleString()}`, "Equity"]} />
            <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="url(#eqGrad)" strokeWidth={2} />
            <defs>
              <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
          </AreaChart>
        </ResponsiveContainer>
      ),
    };
  })
);

const fmt = (n: number | undefined, decimals = 1) => (n != null ? n.toFixed(decimals) : "-");

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [tf, setTf] = useState("1h");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    fetch(`/api/backtest/run/${symbol}?timeframe=${tf}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); setResult(null); }
        else setResult(d);
      })
      .catch(() => setError("Failed to load"))
      .finally(() => setLoading(false));
  }, [symbol, tf]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold">Backtest Engine</h1>
        <select value={symbol} onChange={e => setSymbol(e.target.value)}
          className="bg-[var(--card)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm">
          <option value="BTC/USDT">BTC/USDT</option>
          <option value="ETH/USDT">ETH/USDT</option>
          <option value="XAU/USD">XAU/USD</option>
          <option value="EUR/USD">EUR/USD</option>
        </select>
        <select value={tf} onChange={e => setTf(e.target.value)}
          className="bg-[var(--card)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm">
          <option value="1h">1H</option>
          <option value="4h">4H</option>
          <option value="1d">1D</option>
        </select>
      </div>

      {loading && <p className="text-[var(--muted)] animate-pulse">Running backtest...</p>}
      {error && <p className="text-[var(--red)]">{error}</p>}

      {result && !result.error && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Metric label="Total Return"
              value={`${(result.total_return_pct ?? 0) > 0 ? "+" : ""}${fmt(result.total_return_pct)}%`}
              color={(result.total_return_pct ?? 0) >= 0 ? "#22c55e" : "#ef4444"} />
            <Metric label="Win Rate" value={`${fmt((result.win_rate ?? 0) * 100, 0)}%`} />
            <Metric label="Profit Factor" value={fmt(result.profit_factor, 2)} />
            <Metric label="Sharpe Ratio" value={fmt(result.sharpe_ratio, 2)} />
            <Metric label="Total Trades" value={result.total_trades ?? "-"} />
            <Metric label="Max Drawdown" value={`${fmt(result.max_drawdown_pct)}%`} color="#ef4444" />
            <Metric label="Avg Win" value={`$${fmt(result.avg_win, 0) || "-"}`} color="#22c55e" />
            <Metric label="Final Balance" value={`$${(result.final_balance ?? 0).toLocaleString()}`} />
          </div>

          <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4">Equity Curve</h2>
            <div className="h-80">
              <Suspense fallback={<div className="h-full bg-[var(--border)] rounded animate-pulse" />}>
                <Chart data={result.equity_curve} />
              </Suspense>
            </div>
          </div>

          <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4">Recent Trades</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                    <th className="text-left py-2">Entry</th>
                    <th className="text-left py-2">Exit</th>
                    <th className="text-right py-2">Dir</th>
                    <th className="text-right py-2">Entry $</th>
                    <th className="text-right py-2">Exit $</th>
                    <th className="text-right py-2">PnL</th>
                    <th className="text-right py-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.trades || []).slice(-20).reverse().map((t: any, i: number) => (
                    <tr key={i} className="border-b border-[var(--border)]/50">
                      <td className="py-2">{new Date(t.entry_time).toLocaleDateString()}</td>
                      <td className="py-2">{t.exit_time ? new Date(t.exit_time).toLocaleDateString() : "-"}</td>
                      <td className={`py-2 text-right uppercase text-xs ${t.direction === "long" ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
                        {t.direction}
                      </td>
                      <td className="py-2 text-right">${fmt(t.entry_price, 2)}</td>
                      <td className="py-2 text-right">${fmt(t.exit_price, 2)}</td>
                      <td className={`py-2 text-right font-medium ${(t.pnl ?? 0) >= 0 ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
                        {(t.pnl ?? 0) > 0 ? "+" : ""}{fmt(t.pnl, 2)}
                      </td>
                      <td className="py-2 text-right text-xs text-[var(--muted)]">{t.exit_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4">
      <p className="text-xs text-[var(--muted)] uppercase tracking-wider">{label}</p>
      <p className="text-xl font-bold mt-1" style={{ color: color || "var(--text)" }}>{value}</p>
    </div>
  );
}
