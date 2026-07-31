import type { NextConfig } from "next";

const API_TARGET = process.env.API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  compress: true,

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_TARGET}/api/:path*` },
    ];
  },

  async headers() {
    return [
      {
        source: "/_next/static/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      {
        source: "/:path*",
        headers: [
          { key: "X-DNS-Prefetch-Control", value: "on" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },

  experimental: {
    optimizePackageImports: ["recharts"],
  },
};

export default nextConfig;
