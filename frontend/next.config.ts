import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Production is a static export served by Caddy, which also proxies /api.
// Rewrites are not allowed alongside `output: "export"`, so dev gets them instead.
export default function config(phase: string): NextConfig {
  const base: NextConfig = {
    trailingSlash: true,
    images: { unoptimized: true },
    devIndicators: false,
  };
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    const api = process.env.HALFCA_API_URL ?? "http://127.0.0.1:8000";
    return {
      ...base,
      // FastAPI routes have no trailing slash; keep /api requests as they are.
      skipTrailingSlashRedirect: true,
      // gzip buffers the copilot's server-sent events into one late chunk.
      compress: false,
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
      },
    };
  }
  return { ...base, output: "export" };
}
