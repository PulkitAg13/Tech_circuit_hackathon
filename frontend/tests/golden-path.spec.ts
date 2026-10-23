import { test, expect } from "@playwright/test";

test.describe("CanonGate Golden Path E2E", () => {
  test("complete governance journey: register -> submit -> scan -> finding -> resolve -> audit", async ({
    page,
  }) => {
    const timestamp = Date.now();
    const testUsername = `user_${timestamp}`;
    const testPassword = "Password123!";

    // 1. Open frontend and navigate to login/register
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "CanonGate" })).toBeVisible();

    // 2. Register a new creator account
    await page.getByRole("button", { name: "Register" }).click();
    await page.locator("#username").fill(testUsername);
    await page.locator("#password").fill(testPassword);
    await page.locator("#role").selectOption("creator");
    await page.getByRole("button", { name: "Create Account" }).click();

    // 3. Reach dashboard
    await expect(page.getByRole("heading", { name: "Submissions" })).toBeVisible();
    await expect(page.getByText(testUsername)).toBeVisible();

    // 4. Create a new submission with banned term ('cheap' under acme-corp canon)
    await page.getByRole("button", { name: "+ New Submission" }).click();
    await page.locator("#create-title").fill(`Golden Campaign ${timestamp}`);
    await page
      .locator("#create-content")
      .fill("Our brand offers a cheap product for daily needs.");
    await page.getByRole("button", { name: "Create & Review" }).click();

    // 5. Land on submission detail page
    await expect(page).toHaveURL(/\/submissions\/\d+/);
    await expect(
      page.getByRole("heading", { name: `Golden Campaign ${timestamp}` })
    ).toBeVisible();

    // 6. Trigger real scan via SSE
    const runScanButton = page.getByRole("button", { name: /Run Scan/i });
    await expect(runScanButton).toBeVisible();
    await runScanButton.click();

    // 7. Wait for scan completion and findings to display
    await expect(page.getByRole("button", { name: /Run Scan/i })).toBeVisible({
      timeout: 25000,
    });
    const findingCard = page.locator(".finding-card").first();
    await expect(findingCard).toBeVisible({ timeout: 10000 });
    await expect(findingCard.locator(".ev-del")).toHaveText("cheap");

    // 8. Resolve finding by accepting the suggested fix
    const acceptBtn = page.getByRole("button", { name: /Accept/i });
    await expect(acceptBtn).toBeVisible();
    await acceptBtn.click();

    // 9. Verify finding state is updated to 'accepted' and resolved count reflects it
    await expect(page.locator(".resolution-badge")).toHaveText("accepted", {
      timeout: 10000,
    });
    await expect(page.locator(".stat:has-text('Resolved') .stat-value")).toHaveText(
      "1"
    );

    // 10. Submit for review now that the blocker has been resolved
    await page.getByRole("button", { name: "Submit for Review" }).click();
    await expect(page.locator(".status-badge")).toContainText("in review");

    // 11. Open and verify the cryptographic audit trail
    await page.getByRole("button", { name: /Audit Trail/i }).click();
    await expect(
      page.getByRole("heading", { name: /Audit Trail/i })
    ).toBeVisible();
    await expect(page.locator(".audit-event")).toBeVisible();
    await expect(page.locator(".audit-body")).toContainText("submit: draft → in_review");
    await page.getByRole("button", { name: "Close" }).click();
  });
});
