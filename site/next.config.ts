import type { NextConfig } from "next";

const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  turbopack: { root: import.meta.dirname },
};

export default config;
