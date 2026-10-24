import { test, expect } from "@playwright/test";

test.describe("CanonGate Golden Path E2E", () => {
  test("complete 4-stage governance journey: register -> submit -> scan -> resolve -> brand review -> legal release -> audit", async ({
    page,
  }) => {
    const timestamp = Date.now();
    const testUsername = `user_${timestamp}`;
    const testPassword = "Password123!";

    // 1. Open frontend and navigate to login/register
    await page.goto("/login");
    await expect(page.getByText("CanonGate")).toBeVisible();

    // 2. Switch to Sign Up panel and register a new Creator account with explicit role selection
    await page.getByRole("button", { name: "Create Account" }).click();
    await page.locator("#signup-name").fill("Kabir Roy");
    await page.locator("#signup-username").fill(testUsername);
    await page.locator("#signup-role").selectOption("creator");
    await page.locator("#signup-password").fill(testPassword);
    await page.getByRole("button", { name: /Register & Enter Studio/i }).click();

    // 3. Reach dashboard and verify user identity is preserved
    await expect(page.getByText(`@${testUsername}`)).toBeVisible();

    // 4. Create a new submission with banned term ('cheap' under acme-corp canon)
    await page.getByRole("button", { name: "+ New Campaign Bundle" }).click();
    await page.locator("#sub-title").fill(`Golden Campaign ${timestamp}`);
    await page.locator("#sub-canon").selectOption("acme-corp");
    await page
      .locator("#sub-content")
      .fill("Our brand offers a cheap product for daily enterprise needs.");
    await page
      .getByRole("button", { name: /Create & Open in Split-Screen Review Studio/i })
      .click();

    // 5. Land on submission detail page
    await expect(page).toHaveURL(/\/submissions\/\d+/);
    await expect(
      page.getByRole("heading", { name: `Golden Campaign ${timestamp}` }),
    ).toBeVisible();

    // 6. Trigger real scan via SSE
    const runScanButton = page.getByRole("button", {
      name: /Run Governance Check/i,
    });
    await expect(runScanButton).toBeVisible();
    await runScanButton.click();

    // 7. Wait for scan completion and findings to display
    const findingCard = page.locator(".finding-card").first();
    await expect(findingCard).toBeVisible({ timeout: 15000 });

    // 8. Resolve finding by accepting the suggested fix
    const acceptBtn = page.getByRole("button", { name: /Accept & Apply Fix/i });
    await expect(acceptBtn).toBeVisible();
    await acceptBtn.click();

    // 9. Verify finding state is updated to 'accepted'
    await expect(page.locator(".resolution-badge")).toHaveText("accepted", {
      timeout: 10000,
    });

    // 10. Stage 1 -> Stage 2: Submit for Brand Review
    await page.getByRole("button", { name: /Submit for Brand Review/i }).click();
    await page
      .getByRole("button", { name: /Confirm & Append to Audit Chain/i })
      .click();
    await expect(page.locator(".status-badge").first()).toContainText(
      "in review",
    );

    // 11. Stage 2 -> Stage 3: Switch RBAC Role Mode to Brand Manager (preserving @testUsername!)
    await page.getByRole("button", { name: /2 · Brand Manager/i }).click();
    await expect(page.getByText(`@${testUsername}`)).toBeVisible();
    await page
      .getByRole("button", { name: /Approve Brand Review/i })
      .click();
    await page
      .getByRole("button", { name: /Confirm & Append to Audit Chain/i })
      .click();
    await expect(page.locator(".status-badge").first()).toContainText(
      "approved",
    );

    // 12. Stage 3 -> Stage 4: Switch RBAC Role Mode to Legal Sign-Off and release
    await page.getByRole("button", { name: /3 · Legal Sign-Off/i }).click();
    await page
      .getByRole("button", { name: /Execute Final Legal Sign-Off & Release/i })
      .click();
    await page
      .getByRole("button", { name: /Confirm & Append to Audit Chain/i })
      .click();
    await expect(page.locator(".status-badge").first()).toContainText(
      "published",
    );

    // 13. Open and verify the cryptographic audit trail
    await page.getByRole("button", { name: /Audit Trail/i }).click();
    await expect(
      page.getByRole("heading", { name: /Tamper-Evident SHA-256 Hash Chain/i }),
    ).toBeVisible();
    await expect(page.locator(".audit-event").first()).toBeVisible();
    await page.getByRole("button", { name: /Close/i }).click();
  });
});
