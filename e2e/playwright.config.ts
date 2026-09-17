import { defineConfig, devices } from "@playwright/test";

/**
 * The suite runs against an already-running stack (`docker compose up -d`).
 * Override either origin when pointing it somewhere else:
 *
 *   E2E_BASE_URL=http://localhost:5173 npx playwright test
 */
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

export default defineConfig({
  testDir: "./tests",
  // Each spec creates its own users, so there is no shared state to serialise.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"], ["html", { open: "never" }]],
  timeout: 30_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
