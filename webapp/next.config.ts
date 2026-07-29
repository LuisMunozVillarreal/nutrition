import type { NextConfig } from "next";

const graphqlEndpoint = (
  process.env.GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/graphql",
        destination: `${graphqlEndpoint}/`,
      },
      {
        source: "/graphql/:path*",
        destination: `${graphqlEndpoint}/:path*`,
      },
    ];
  },
};

export default nextConfig;
