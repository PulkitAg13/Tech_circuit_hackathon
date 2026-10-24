import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isWin = process.platform === "win32";
const pythonVenv = path.resolve(
  __dirname,
  isWin ? "../backend/.venv/Scripts/python.exe" : "../backend/.venv/bin/python"
);

export default defineConfig({
  testDir: "./tests",
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `"${pythonVenv}" -m uvicorn canongate.api.app:app --port 8000`,
      url: "http://localhost:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
      cwd: path.resolve(__dirname, "../backend"),
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
      cwd: __dirname,
    },
  ],
});
