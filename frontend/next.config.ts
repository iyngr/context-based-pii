import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  output: 'standalone',
  async headers() {
    return [
      {
        // Apply these headers to all routes
        source: '/(.*)',
        headers: [
          {
            key: 'Cross-Origin-Opener-Policy',
            value: 'same-origin-allow-popups',
          },
        ],
      },
    ];
  },
  env: {
    // Make backend URLs available to API routes (server-side)
    BACKEND_SERVICE_URL: process.env.NEXT_PUBLIC_BACKEND_URL,
    TRANSCRIPT_AGGREGATOR_URL: process.env.NEXT_PUBLIC_TRANSCRIPT_AGGREGATOR_URL,
  },
};

export default nextConfig;
