import { expect, test } from "@playwright/test";

test.beforeAll(async ({ request }) => {
  const health = await request.get("http://127.0.0.1:8000/healthz");
  expect(health.ok()).toBe(true);
});

test("real seeded catalog provides a server quote without inventing payment", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Made by you. Found by AI." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Explore the demo collection" }).click();
  await expect(
    page.getByRole("heading", { name: "Meera's Jaipur Studio" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Indigo block print scarf" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Get a quote for Indigo block print scarf" })
    .click();
  await page.getByRole("button", { name: /Indigo block print scarf/ }).click();
  await expect(page.getByText("YOUR SERVER-VERIFIED QUOTE")).toBeVisible();
  await expect(
    page.getByRole("definition").filter({ hasText: "$55.00 USD" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Confirm total & continue to PayPal" }),
  ).toBeDisabled();
  await expect(
    page.getByText(
      "Checkout needs PayPal sandbox credentials. No payment has been created.",
    ),
  ).toBeVisible();
});

test("mobile pages fit a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of [
    "/",
    "/s/meera-jaipur",
    "/playground",
    "/onboarding",
    "/dashboard",
  ]) {
    await page.goto(path);
    await expect(page.locator("h1")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
});
