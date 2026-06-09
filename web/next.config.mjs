const apiTarget = process.env.FREECADAI_API_BASE_URL || "http://127.0.0.1:8000";
const assetPrefix = process.env.NEXT_PUBLIC_ASSET_PREFIX || "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  assetPrefix,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiTarget}/api/:path*` },
      { source: "/health", destination: `${apiTarget}/health` }
    ];
  }
};

export default nextConfig;
