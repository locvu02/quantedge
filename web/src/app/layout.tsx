import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuantEdge - AI Trading Platform",
  description: "AI-powered automated trading system for Forex & Crypto. 70%+ win rate with ML-driven signals.",
  keywords: ["trading bot", "AI trading", "crypto", "forex", "automated trading", "machine learning"],
  openGraph: {
    title: "QuantEdge - AI Trading Platform",
    description: "AI-powered automated trading system with 70%+ win rate",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">
        <nav className="border-b border-[var(--border)] bg-[var(--card)] px-6 py-4">
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <h1 className="text-xl font-bold tracking-tight">
              <span className="text-[var(--accent)]">Quant</span>Edge
            </h1>
            <div className="flex gap-4 text-sm text-[var(--muted)]">
              <a href="/" className="hover:text-[var(--text)] transition-colors">Dashboard</a>
              <a href="/signals" className="hover:text-[var(--text)] transition-colors">Signals</a>
              <a href="/backtest" className="hover:text-[var(--text)] transition-colors">Backtest</a>
            </div>
          </div>
        </nav>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
