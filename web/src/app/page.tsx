"use client";

import { useEffect, useState, lazy, Suspense } from "react";

const API = "/api";

const Chart = lazy(() =>
  import("recharts").then(mod => {
    const { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } = mod;
    return {
      default: ({ data }: { data: any[] }) => (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1e1e2e" strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" tick={false} />
            <YAxis stroke="#64748b" fontSize={12} />
            <Tooltip
              contentStyle={{
                background: "#12121a",
                border: "1px solid #1e1e2e",
                borderRadius: "8px",
                color: "#e2e8f0",
              }}
              formatter={(v: number) => [`$${v.toLocaleString()}`, "Equity"]}
            />
            <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="url(#equityGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      ),
    };
  })
);

const fmt = (n: number | undefined, decimals = 1) => (n != null ? n.toFixed(decimals) : "-");

function useApi<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    fetch(url).then(r => r.json()).then(setData).catch(() => {});
  }, [url]);
  return data;
}

export default function Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = useState("BTC/USDT");
  const [selectedTf, setSelectedTf] = useState("1h");
  const [equityData, setEquityData] = useState<any[]>([]);

  const btData = useApi<any>(`${API}/backtest/scan?timeframe=1h`);
  const sigData = useApi<any>(`${API}/signals/scan?timeframe=1h`);

  const backtests = (btData?.results || []).filter((r: any) => r.total_return_pct != null);
  const signals = (sigData?.results || []).filter((r: any) => r.signal).map((r: any) => ({ symbol: r.symbol, ...r.signal }));

  useEffect(() => {
    fetch(`${API}/backtest/run/${selectedSymbol}?timeframe=${selectedTf}`)
      .then(r => r.json())
      .then(d => { if (d.equity_curve) setEquityData(d.equity_curve); })
      .catch(() => {});
  }, [selectedSymbol, selectedTf]);

  const totalReturn = backtests.reduce((s: number, b: any) => s + (b.total_return_pct ?? 0), 0);
  const avgWinRate = backtests.length ? backtests.reduce((s: number, b: any) => s + (b.win_rate ?? 0), 0) / backtests.length : 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card label="Total Return" value={`${totalReturn.toFixed(1)}%`} color={totalReturn >= 0 ? "#22c55e" : "#ef4444"} />
        <Card label="Avg Win Rate" value={`${(avgWinRate * 100).toFixed(0)}%`} />
        <Card label="Active Signals" value={String(signals.length)} />
        <Card label="Symbols Tracked" value="4" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Equity Curve</h2>
            <div className="flex gap-2">
              {["BTC/USDT", "ETH/USDT"].map(s => (
                <button key={s} onClick={() => setSelectedSymbol(s)}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    selectedSymbol === s ? "bg-[var(--accent)] text-white" : "bg-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]"
                  }`}>
                  {s.split("/")[0]}
                </button>
              ))}
              <select value={selectedTf} onChange={e => setSelectedTf(e.target.value)}
                className="bg-[var(--border)] text-[var(--muted)] text-xs rounded px-2 py-1">
                <option value="1h">1H</option>
                <option value="4h">4H</option>
              </select>
            </div>
          </div>
          <div className="h-64">
            <Suspense fallback={<div className="h-full bg-[var(--border)] rounded animate-pulse" />}>
              <Chart data={equityData} />
            </Suspense>
          </div>
        </div>

        <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">Signals</h2>
          {signals.length === 0 ? (
            <p className="text-[var(--muted)] text-sm">No active signals</p>
          ) : (
            <div className="space-y-3">
              {signals.map((s: any, i: number) => (
                <div key={i} className="p-3 rounded-lg bg-[var(--bg)] border border-[var(--border)]">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{s.symbol}</span>
                    <span className={`text-xs font-bold uppercase ${s.direction === "long" ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
                      {s.direction}
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-1 text-xs text-[var(--muted)]">
                    <span>Entry: ${s.entry_price?.toFixed(2)}</span>
                    <span>Conf: {(s.confidence * 100).toFixed(0)}%</span>
                    <span>SL: ${s.stop_loss?.toFixed(2)}</span>
                    <span>TP: ${s.take_profit?.toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Backtest Results (1H)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--muted)] border-b border-[var(--border)]">
                <th className="text-left py-2">Symbol</th>
                <th className="text-right py-2">Return</th>
                <th className="text-right py-2">Win Rate</th>
                <th className="text-right py-2">Trades</th>
                <th className="text-right py-2">PF</th>
                <th className="text-right py-2">Max DD</th>
                <th className="text-right py-2">Sharpe</th>
                <th className="text-right py-2">Balance</th>
              </tr>
            </thead>
            <tbody>
              {backtests.map((b: any) => (
                <tr key={b.symbol} className="border-b border-[var(--border)]/50">
                  <td className="py-3 font-medium">{b.symbol}</td>
                  <td className={`py-3 text-right ${(b.total_return_pct ?? 0) >= 0 ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
                    {(b.total_return_pct ?? 0) > 0 ? "+" : ""}{fmt(b.total_return_pct)}%
                  </td>
                  <td className="py-3 text-right">{fmt((b.win_rate ?? 0) * 100, 0)}%</td>
                  <td className="py-3 text-right">{b.total_trades ?? "-"}</td>
                  <td className="py-3 text-right">{fmt(b.profit_factor, 2)}</td>
                  <td className="py-3 text-right text-[var(--red)]">{fmt(b.max_drawdown_pct)}%</td>
                  <td className="py-3 text-right">{fmt(b.sharpe_ratio, 2)}</td>
                  <td className="py-3 text-right">${(b.final_balance ?? 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Card({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5">
      <p className="text-xs text-[var(--muted)] uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-bold mt-1" style={{ color: color || "var(--text)" }}>{value}</p>
    </div>
  );
}
