import type { NextConfig } from "next";

// The browser talks to one origin: /api is forwarded to the API, so the session cookie is first-party.
// In development /s3 is forwarded to a local S3 emulator; in production presigned URLs point at S3/R2 directly.
const api = process.env.API_URL ?? "http://localhost:8000";
const devS3 = process.env.DEV_S3_URL;

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // gzip would buffer the live event stream (SSE); the CDN / reverse proxy compresses everything else in production
  compress: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      ...(devS3 ? [{ source: "/s3/:path*", destination: `${devS3}/:path*` }] : []),
    ];
  },
  images: { unoptimized: true },
};

export default config;
