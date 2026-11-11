import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  agentRules: false,
  devIndicators: false,
  async headers() {
    // Art is shipped with the app; revision its URL when replacing its contents.
    // Keep API routes (including their no-store responses) outside this rule.
    return ["/atlas-:name.webp", "/home-wave.webp", "/login-ribbon.webp", "/knowledge-contours.svg"].map((source) => ({
      source,
      headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
    }));
  },
};
export default config;
