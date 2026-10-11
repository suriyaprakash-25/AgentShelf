import { expect, test } from "@playwright/test";

const publicDsn = `https://${"a".repeat(32)}@o999.ingest.sentry.io/999`;

for (const status of [200, 503]) {
  test(`monitoring ${status === 200 ? "disabled" : "unavailable"} preserves catalog without loading its SDK`, async ({
    page,
  }) => {
    const monitoringRequests: string[] = [];
    page.on("request", (request) => {
      if (/monitoring-sdk|@sentry|ingest\.sentry\.io/.test(request.url()))
        monitoringRequests.push(request.url());
    });
    await page.route("**/api/monitoring-config", (route) =>
      route.fulfill({ status, json: { dsn: null, environment: "test" } }),
    );
    const configuration = page.waitForResponse("**/api/monitoring-config");
    await page.goto("/");
    await configuration;
    await page
      .getByRole("link", { name: "Explore the demo collection" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Indigo block print scarf" }),
    ).toBeVisible();
    expect(monitoringRequests).toEqual([]);
  });
}

test("actual browser SDK sends only fixed codes and deduplicates errors", async ({
  page,
}) => {
  const envelopes: string[] = [];
  await page.route("**/api/monitoring-config", (route) =>
    route.fulfill({ json: { dsn: publicDsn, environment: "test" } }),
  );
  await page.route("https://o999.ingest.sentry.io/**", (route) => {
    envelopes.push(route.request().postDataBuffer()?.toString("utf8") || "");
    return route.fulfill({ status: 200, json: {} });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.evaluate(() => {
    for (let n = 0; n < 5; n++)
      window.dispatchEvent(
        new ErrorEvent("error", {
          message: "private-email@example.test private-address secret-value",
          filename: "https://private.example.test/#login-token",
          error: new Error("private-error-content"),
        }),
      );
    window.dispatchEvent(
      new PromiseRejectionEvent("unhandledrejection", {
        promise: Promise.resolve(),
        reason: "private-rejection-secret",
      }),
    );
  });
  await expect
    .poll(
      () => envelopes.filter((body) => body.includes('"type":"event"')).length,
    )
    .toBe(2);
  const bodies = envelopes.join("\n");
  expect(bodies).toContain("agentshelf:BROWSER_RUNTIME_ERROR");
  expect(bodies).toContain("agentshelf:BROWSER_UNHANDLED_REJECTION");
  expect(bodies).not.toMatch(
    /private-|secret-value|login-token|"breadcrumbs"|"request"|"user"|"exception"|"contexts"/,
  );
});

test("render failures show a usable recovery screen and emit a fixed code", async ({
  page,
}) => {
  const envelopes: string[] = [];
  await page.route("**/api/monitoring-config", (route) =>
    route.fulfill({ json: { dsn: publicDsn, environment: "test" } }),
  );
  await page.route("https://o999.ingest.sentry.io/**", (route) => {
    envelopes.push(route.request().postDataBuffer()?.toString("utf8") || "");
    return route.fulfill({ status: 200, json: {} });
  });
  await page.route("**/api/ops", (route) =>
    route.fulfill({ json: { workers: null } }),
  );
  await page.route("**/api/me", (route) =>
    route.fulfill({ json: { csrf_token: "controlled-csrf" } }),
  );
  await page.goto("/operations");
  await expect(
    page.getByRole("heading", { name: "This screen could not load." }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload page" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "review your existing order",
  );
  await expect
    .poll(() =>
      envelopes.some((body) => body.includes("agentshelf:UI_RENDER_FAILURE")),
    )
    .toBe(true);
  expect(envelopes.join("\n")).not.toMatch(
    /"exception"|"breadcrumbs"|"request"|controlled-csrf/,
  );
});

test("browser privacy filter drops arbitrary events and removes attachments", async ({
  page,
}) => {
  await page.route("**/api/monitoring-config", (route) =>
    route.fulfill({ json: { dsn: null, environment: "test" } }),
  );
  await page.goto("/");
  const result = await page.evaluate(async () => {
    // Exercise the application filter itself through Vite's local module server.
    const modulePath = "/src/telemetry.ts";
    const { scrubBrowserEvent } = await import(modulePath);
    const hint = {
      attachments: [{ filename: "private-photo.jpg", data: "private-data" }],
    };
    const filtered = scrubBrowserEvent(
      {
        message: "agentshelf:UI_RENDER_FAILURE",
        event_id: "private-email@example.test",
        timestamp: "private-value",
        user: { email: "private-email@example.test" },
        request: { url: "https://private.example.test/#token" },
        exception: { values: [{ value: "private-address" }] },
        breadcrumbs: [{ message: "private-form" }],
        extra: { token: "private-token" },
      },
      hint,
    );
    return {
      filtered,
      attachments: hint.attachments,
      rejected: scrubBrowserEvent({ message: "private-message" }, {}),
    };
  });
  expect(result.filtered).toEqual({
    level: "error",
    message: "agentshelf:UI_RENDER_FAILURE",
    platform: "javascript",
    environment: "local",
  });
  expect(result.attachments).toEqual([]);
  expect(result.rejected).toBeNull();
});
