import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";
import { writeFile } from "node:fs/promises";

let scanNumber = 0;

export async function scanAccessibility(page: Page, info: TestInfo) {
  await page.evaluate(() => document.fonts.ready);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const output = info.outputPath(`accessibility-${++scanNumber}.json`);
  await writeFile(
    output,
    JSON.stringify({
      screen: new URL(page.url()).pathname,
      viewport: page.viewportSize(),
      violations: results.violations,
      incomplete: results.incomplete,
    }),
  );
  await info.attach("accessibility-results", {
    path: output,
    contentType: "application/json",
  });
  expect.soft(results.violations).toEqual([]);
}
