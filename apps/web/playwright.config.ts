import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 12_000 },
  reporter: "list",
  use: {
    actionTimeout: 15_000,
    baseURL: process.env.KNOWFLOW_E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
});
