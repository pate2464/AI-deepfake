/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Dev rewrites proxy to FastAPI; default proxy timeout is 30s which breaks long /analyze runs.
  experimental: {
    proxyTimeout: 1_800_000, // 30 minutes (ms)
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
