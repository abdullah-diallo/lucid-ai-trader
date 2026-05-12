/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  serverExternalPackages: ["node-telegram-bot-api", "yahoo-finance2"],
  async headers() {
    return [
      {
        source: "/api/webhook/:path*",
        headers: [{ key: "Cache-Control", value: "no-store" }],
      },
    ];
  },
};

export default nextConfig;
