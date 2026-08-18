const AxeBuilder = require("@axe-core/playwright").default;
const { expect, test } = require("@playwright/test");

function violationSummary(violations) {
  return violations
    .map(
      (violation) =>
        `${violation.id} (${violation.impact || "impact unknown"}): ${violation.help}; ` +
        violation.nodes.map((node) => node.target.join(" ")).join(", "),
    )
    .join("\n");
}

async function siteManifest(request, baseUrl) {
  const response = await request.get(new URL("site-manifest.json", baseUrl).href);
  expect(response.ok(), "generated-site manifest must be available").toBeTruthy();
  return response.json();
}

test("every generated page passes structural and automated accessibility contracts", async ({
  page,
  request,
}) => {
  const baseUrl = process.env.SPRINT_CI_SITE_URL;
  expect(baseUrl).toBeTruthy();
  const manifest = await siteManifest(request, baseUrl);

  for (const entry of manifest.pages) {
    await test.step(`${entry.id}: landmarks, status, navigation, and axe`, async () => {
      await page.goto(new URL(entry.path, baseUrl).href);
      await expect(page.locator("main#main")).toHaveCount(1);
      await expect(page.locator("h1")).toHaveCount(1);
      await expect(page.getByRole("navigation", { name: "Sprint site" })).toHaveCount(1);
      await expect(page.locator('[aria-current="page"]')).toHaveCount(1);
      await expect(page.getByRole("link", { name: "Skip to content" })).toHaveCount(1);
      await expect(page.locator(".status").first()).toBeVisible();

      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations, violationSummary(results.violations)).toEqual([]);
    });
  }
});

test.describe("narrow responsive behavior", () => {
  test.use({ viewport: { width: 320, height: 568 } });

  test("all pages contain overflow and preserve keyboard interactions", async ({
    page,
    request,
  }) => {
    const baseUrl = process.env.SPRINT_CI_SITE_URL;
    const manifest = await siteManifest(request, baseUrl);
    for (const entry of manifest.pages) {
      await test.step(`${entry.id}: no page-level horizontal overflow`, async () => {
        await page.goto(new URL(entry.path, baseUrl).href);
        const dimensions = await page.evaluate(() => ({
          clientWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
        }));
        expect(dimensions.scrollWidth, `${entry.id} overflowed the viewport`).toBeLessThanOrEqual(
          dimensions.clientWidth,
        );
      });
    }

    const tablePage = manifest.pages.find((entry) => entry.id === "03-foundation");
    expect(tablePage, "manifest must include the foundation table fixture").toBeTruthy();
    await page.goto(new URL(tablePage.path, baseUrl).href);
    const tableRegion = page.locator(".table-scroll").first();
    await expect(tableRegion).toBeVisible();
    await expect(tableRegion).toHaveAttribute("aria-label");
    await expect(tableRegion).toHaveAttribute("tabindex", "0");
    const tableDimensions = await tableRegion.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(tableDimensions.scrollWidth).toBeGreaterThan(tableDimensions.clientWidth);

    await page.keyboard.press("Home");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("main#main")).toBeFocused();

    await page.goto(baseUrl);
    const guidance = page.locator("details.guidance").first();
    await expect(guidance).not.toHaveAttribute("open", "");
    await guidance.locator("summary").click();
    await expect(guidance).toHaveAttribute("open", "");
  });
});

test("manifest navigation works from a deep nested artifact", async ({ page, request }) => {
  const baseUrl = process.env.SPRINT_CI_SITE_URL;
  const manifest = await siteManifest(request, baseUrl);
  const artifact = manifest.pages.find((entry) => entry.id === "04-journey-map");
  expect(artifact, "manifest must include a nested journey-map artifact").toBeTruthy();
  await page.goto(new URL(artifact.path, baseUrl).href);

  const navigation = page.getByRole("navigation", { name: "Sprint site" });
  await navigation.getByRole("link", { name: /^Home$/ }).click();
  await expect(page).toHaveURL(new URL("index.html", baseUrl).href);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Synthetic renderer");

  const next = manifest.pages.find((entry) => entry.id === "01-sprint-brief");
  expect(next, "manifest must include the first navigable artifact").toBeTruthy();
  await page.goto(new URL(next.path, baseUrl).href);
  await navigation.getByRole("link", { name: /^Next:/ }).click();
  await expect(page).toHaveURL(new URL("artifacts/02-evidence-ledger.html", baseUrl).href);
});
