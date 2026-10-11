import { expect, test } from "@playwright/test";

test("controlled AI stream requires human quote confirmation before checkout", async ({
  page,
}) => {
  let checkouts = 0;
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({
      json: {
        paypal_mode: "sandbox",
        ai_configured: true,
        checkout_configured: true,
      },
    }),
  );
  await page.route("**/api/playground/sessions", (route) =>
    route.fulfill({ json: { session_id: "controlled-buyer-session" } }),
  );
  await page.route("**/api/playground/chat", async (route) => {
    const body = route.request().postDataJSON();
    const events = body.confirmed_quote_id
      ? (checkouts++,
        [
          {
            type: "checkout",
            order_id: "controlled-order",
            approval_url:
              "https://www.sandbox.paypal.com/checkoutnow?token=CONTROLLED",
          },
          { type: "done" },
        ])
      : [
          { type: "tool_call", name: "get_quote", arguments: { qty: 1 } },
          {
            type: "tool_result",
            name: "get_quote",
            result: { total: "55.00", currency: "USD" },
          },
          {
            type: "quote",
            quote_id: "controlled-quote",
            title: "Blue scarf",
            qty: 1,
            total: "55.00",
            shipping: "10.00",
            currency: "USD",
            ship_to_country: "GB",
            expires_at: new Date(Date.now() + 60000).toISOString(),
          },
          { type: "message", text: "Review your scarf quote 🎁." },
          { type: "done" },
        ];
    await route.fulfill({
      contentType: "text/event-stream",
      body: events
        .map((event) => `data: ${JSON.stringify(event)}\n\n`)
        .join(""),
    });
  });
  await page.goto("/playground");
  await page.getByLabel("Your request").fill("Find a blue scarf");
  await page.getByRole("button", { name: "Ask the agent" }).click();
  await expect(page.getByText("Review your scarf quote 🎁.")).toBeVisible();
  expect(checkouts).toBe(0);
  await expect(
    page.getByText("Total: $55.00 USD, including $10.00 shipping to GB."),
  ).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByText("MCP tool activity (2)").click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Confirm this quote and create checkout" })
    .click();
  await expect(
    page.getByRole("link", { name: "Approve payment on PayPal" }),
  ).toHaveAttribute(
    "href",
    "https://www.sandbox.paypal.com/checkoutnow?token=CONTROLLED",
  );
  expect(checkouts).toBe(1);
  expect(page.url()).toContain("/playground");
});

test("controlled listing review uses seller price and explicit publication", async ({
  page,
}) => {
  let published: Record<string, unknown> | null = null;
  await page.route("**/api/me", (route) =>
    route.fulfill({
      json: {
        name: "Controlled seller fixture",
        store_slug: "fixture",
        csrf_token: "fixture-csrf",
        is_operator: false,
      },
    }),
  );
  await page.route("**/api/me/products?*", (route) =>
    route.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route("**/api/me/orders?*", (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route("**/api/me/listings", (route) =>
    route.fulfill({
      status: route.request().method() === "POST" ? 202 : 200,
      json:
        route.request().method() === "POST"
          ? { id: "fixture-listing" }
          : { items: [] },
    }),
  );
  await page.route("**/api/me/media", (route) =>
    route.fulfill({ status: 201, json: { id: "fixture-media" } }),
  );
  await page.route("**/api/me/listings/fixture-listing", (route) =>
    route.fulfill({
      json: {
        id: "fixture-listing",
        status: "drafted",
        media_urls: [],
        draft: {
          title: "Blue scarf",
          description: "Blue textile",
          suggested_price_minor: 4500,
          price_rationale: "Seller review required.",
          questions: [],
        },
      },
    }),
  );
  await page.route(
    "**/api/me/listings/fixture-listing/publish",
    async (route) => {
      published = route.request().postDataJSON();
      await route.fulfill({
        json: { status: "live", product_id: "fixture-product" },
      });
    },
  );
  await page.goto("/dashboard");
  await page.getByLabel("Product photos (one to four)").setInputFiles({
    name: "product.png",
    mimeType: "image/png",
    buffer: Buffer.from("controlled upload fixture"),
  });
  await page.getByRole("button", { name: "Generate a draft" }).click();
  await expect(
    page.getByText("Suggested price: $45.00 USD.", { exact: false }),
  ).toBeVisible();
  expect(published).toBeNull();
  await page.getByLabel("Your selling price in USD").fill("39.00");
  await page.getByLabel("Available stock", { exact: true }).first().fill("2");
  await page
    .getByLabel("I reviewed these details and confirm my price and stock.")
    .check();
  await page
    .getByRole("button", { name: "Confirm and publish listing" })
    .click();
  await expect(
    page.getByText("Published. Your product is now in your public store."),
  ).toBeVisible();
  expect(published).toMatchObject({
    confirm: true,
    price_minor: 3900,
    stock: 2,
  });
});

test("AG Studio renders controlled aggregates or enforces the production licence gate", async ({
  page,
}, testInfo) => {
  const studioRequests: string[] = [];
  page.on("request", (request) => {
    if (/AnalyticsStudio|ag-studio|\/api\/me\/analytics/.test(request.url()))
      studioRequests.push(request.url());
  });
  await page.route("**/api/me", (route) =>
    route.fulfill({
      json: {
        name: "Studio fixture",
        store_slug: "fixture",
        csrf_token: "fixture-csrf",
        is_operator: false,
      },
    }),
  );
  await page.route("**/api/me/products?*", (route) =>
    route.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route("**/api/me/orders?*", (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route("**/api/me/listings", (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route("**/api/me/analytics", (route) =>
    route.fulfill({
      json: {
        currency: "USD",
        products: [{ status: "live", count: 3, available_stock: 7 }],
        orders: [{ status: "paid", count: 2, gross_amount_minor: 9000 }],
        notice: "Gross amounts are not net revenue.",
      },
    }),
  );
  await page.route("**/api/me/analytics/chat", async (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe("fixture-csrf");
    expect(Object.keys(route.request().postDataJSON())).toEqual(["message"]);
    await route.fulfill({
      json: {
        text: "Your shop has seven available units and two paid orders.",
      },
    });
  });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Open shop analytics" }).click();
  if (testInfo.project.name === "production-without-license") {
    await expect(
      page.getByText("Analytics Studio requires a deployment licence.", {
        exact: false,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "Create a product draft",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator(".analytics-studio")).toHaveCount(0);
    expect(studioRequests).toEqual([]);
    return;
  }
  await expect(
    page.getByText("Available stock: 7", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByText("3 live products", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/2 paid orders.*90.00 USD gross/)).toBeVisible();
  await page.getByText("Summarize my shop", { exact: true }).click();
  await expect(
    page.getByText("Your shop has seven available units and two paid orders.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(studioRequests.some((url) => url.includes("/api/me/analytics"))).toBe(
    true,
  );
  await page.locator(".analytics-studio").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../work/studio-desktop.png",
    fullPage: false,
  });
});
