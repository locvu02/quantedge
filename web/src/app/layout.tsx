import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { NavBar } from "./nav";

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
        <AuthProvider>
          <NavBar />
          <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
