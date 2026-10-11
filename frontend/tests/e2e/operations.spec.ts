import { expect, test } from "@playwright/test";

const orderId = "11111111-1111-4111-8111-111111111111";
const jobId = "22222222-2222-4222-8222-222222222222";

const empty = {
  adjustments: [],
  failed_total: 0,
  failed_jobs: [],
  orders: [],
  workers: [],
};

test("controlled operator recovery requires confirmation, sends CSRF and preserves a failed review", async ({
  page,
}) => {
  let correlated = false;
  const submissions: { body: unknown; csrf: string | undefined }[] = [];
  await page.route("**/api/me", (route) =>
    route.fulfill({ json: { csrf_token: "operator-fixture-csrf" } }),
  );
  await page.route("**/api/ops", (route) =>
    route.fulfill({
      json: {
        ...empty,
        workers: [{ name: "main", age_seconds: 100 }],
        orders: [
          {
            id: orderId,
            status: "checkout_created",
            code: "CREATE_RESPONSE_UNKNOWN",
            paypal_order_id: correlated ? "PAYPAL-REFERENCE" : null,
          },
        ],
      },
    }),
  );
  await page.route(`**/api/ops/orders/${orderId}/correlate`, (route) => {
    submissions.push({
      body: route.request().postDataJSON(),
      csrf: route.request().headers()["x-csrf-token"],
    });
    if (submissions.length === 1)
      return route.fulfill({
        status: 409,
        json: {
          error: {
            message:
              "The provider amount does not match. Review the PayPal order.",
          },
        },
      });
    correlated = true;
    return route.fulfill({ json: { paypal_order_id: "PAYPAL-REFERENCE" } });
  });
  await page.goto("/operations");
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByText(/investigate worker health/)).toBeVisible();
  await page
    .getByLabel("PayPal order reference found during provider review")
    .fill("PAYPAL-REFERENCE");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Verify reference" }).click();
  expect(submissions).toHaveLength(0);
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("does not approve or capture payment");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Verify reference" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "The provider amount does not match. Review the PayPal order.",
  );
  await expect(
    page.getByRole("button", { name: "Verify reference" }),
  ).toBeEnabled();
  expect(submissions[0]).toEqual({
    body: { paypal_order_id: "PAYPAL-REFERENCE", confirmed: true },
    csrf: "operator-fixture-csrf",
  });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Verify reference" }).click();
  await expect(
    page.getByText("PayPal reference: PAYPAL-REFERENCE"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Verify reference" }),
  ).toHaveCount(0);
  expect(submissions).toHaveLength(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("controlled failed-job retry requires confirmation and refreshes empty states", async ({
  page,
}) => {
  let retries = 0;
  await page.route("**/api/me", (route) =>
    route.fulfill({ json: { csrf_token: "operator-fixture-csrf" } }),
  );
  await page.route("**/api/ops", (route) =>
    route.fulfill({
      json: {
        ...empty,
        failed_total: retries ? 0 : 1,
        failed_jobs: retries
          ? []
          : [
              {
                id: jobId,
                kind: "whatsapp_send",
                attempts: 5,
                code: "WHATSAPP_UNAVAILABLE",
              },
            ],
      },
    }),
  );
  await page.route(`**/api/ops/jobs/${jobId}/retry`, (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe(
      "operator-fixture-csrf",
    );
    expect(route.request().postDataJSON()).toEqual({});
    retries++;
    return route.fulfill({ json: { status: "queued" } });
  });
  await page.goto("/operations");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Retry job" }).click();
  expect(retries).toBe(0);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Retry job" }).click();
  await expect(page.getByText("No failed jobs to review.")).toBeVisible();
  await expect(
    page.getByText("No refunds or disputes recorded."),
  ).toBeVisible();
  await expect(
    page.getByText("No payment orders awaiting review."),
  ).toBeVisible();
  expect(retries).toBe(1);
});

test("controlled access denial hides operator recovery controls", async ({
  page,
}) => {
  await page.route("**/api/me", (route) =>
    route.fulfill({ json: { csrf_token: "ordinary-seller-fixture" } }),
  );
  await page.route("**/api/ops", (route) =>
    route.fulfill({
      status: 403,
      json: { error: { message: "Operator access is required." } },
    }),
  );
  await page.goto("/operations");
  await expect(page.getByRole("alert")).toHaveText(
    "Operator access is required.",
  );
  await expect(
    page.getByRole("button", { name: /Retry job|Verify reference/ }),
  ).toHaveCount(0);
});
