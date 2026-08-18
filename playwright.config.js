const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/browser",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "line",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  globalSetup: require.resolve("./tests/browser/global-setup"),
  use: {
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
  },
});
