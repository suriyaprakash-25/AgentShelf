import { expect, test } from "@playwright/test";
import { scanAccessibility as scan } from "../accessibility";

test("public screens pass automated accessibility checks on mobile", async ({
  page,
}, info) => {
  test.setTimeout(90000);
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of [
    "/",
    "/s/meera-jaipur",
    "/playground",
    "/onboarding",
    "/dashboard",
    "/operations",
    "/receipt",
    "/missing-page",
  ]) {
    await test.step(path, async () => {
      await page.goto(path);
      await expect(page.locator("h1")).toBeVisible();
      await expect(page.getByText("Loading your workspace…")).toHaveCount(0);
      await scan(page, info);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    });
  }
});

test("keyboard skip link moves focus to main content", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
});

test("controlled authenticated seller and operator screens pass accessibility checks", async ({
  page,
}, info) => {
  test.setTimeout(60000);
  await page.route("**/api/me", (route) =>
    route.fulfill({
      json: {
        name: "Accessibility fixture",
        store_slug: "fixture",
        csrf_token: "fixture-csrf",
        is_operator: true,
      },
    }),
  );
  await page.route("**/api/me/products?*", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "fixture-product",
            title: "Accessible scarf",
            price_minor: 4500,
            stock: 2,
            status: "live",
          },
        ],
        total: 1,
      },
    }),
  );
  await page.route("**/api/me/orders?*", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: "fixture-order",
            status: "paid",
            amount_minor: 5500,
            currency: "USD",
            created_at: "2026-10-11T10:00:00Z",
          },
        ],
      },
    }),
  );
  await page.route("**/api/me/listings", (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route("**/api/me/analytics", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { message: "Unavailable in controlled evaluation" } },
    }),
  );
  await page.route("**/api/ops", (route) =>
    route.fulfill({
      json: {
        adjustments: [],
        failed_total: 0,
        failed_jobs: [],
        orders: [],
        workers: [{ name: "main", age_seconds: 10 }],
      },
    }),
  );
  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 812 });
    for (const path of ["/dashboard", "/operations"]) {
      await page.goto(path);
      await expect(page.locator("h1")).toBeVisible();
      await expect(
        page.getByRole("heading", {
          name:
            path === "/dashboard"
              ? "Create a product draft"
              : "Worker heartbeat",
        }),
      ).toBeVisible();
      if (path === "/dashboard") {
        await expect(
          page.getByRole("gridcell", { name: "Accessible scarf" }),
        ).toBeVisible();
        await expect(page.getByLabel("Tracking number")).toBeVisible();
      }
      await scan(page, info);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
});
