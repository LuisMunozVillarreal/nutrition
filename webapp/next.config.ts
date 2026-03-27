import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: '/graphql',
        destination: 'http://localhost:8000/graphql/',
      },
      {
        source: '/graphql/:path+',
        destination: 'http://localhost:8000/graphql/:path+',
      },
    ];
  },
};

export default nextConfig;
