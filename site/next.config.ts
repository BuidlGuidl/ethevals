import type { NextConfig } from "next";

const config: NextConfig = {
  agentRules: false,
  output: "export",
  trailingSlash: true,
  turbopack: { root: import.meta.dirname },
};

export default config;
