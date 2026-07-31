import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  poweredByHeader: false,
  compress: true,
  images: { unoptimized: true },

  experimental: {
    optimizePackageImports: ["recharts"],
  },
};

export default nextConfig;
