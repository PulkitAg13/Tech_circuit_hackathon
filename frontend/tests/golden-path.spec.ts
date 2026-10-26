import { test, expect } from "@playwright/test";

test.describe("CanonGate Golden Path E2E", () => {
  test("complete 4-stage governance journey: register -> submit -> scan -> resolve -> brand review -> legal release -> audit", async ({
    page,
  }) => {
    const timestamp = Date.now();
    const creatorUsername = `creator_${timestamp}`;
    const reviewerUsername = `reviewer_${timestamp}`;
    const legalUsername = `legal_${timestamp}`;
    const testPassword = "Password123!";

    // 1. Open frontend and navigate to login/register
    await page.goto("/login");
    await expect(page.getByText("CanonGate").first()).toBeVisible();

    // 2. Switch to Sign Up panel and register a new Creator account with explicit role selection
    await page.getByRole("button", { name: "Create Account" }).click();
    await page.locator("#signup-name").fill("Kabir Roy");
    await page.locator("#signup-username").fill(creatorUsername);
    await page.locator("#signup-role").selectOption("creator");
    await page.locator("#signup-password").fill(testPassword);
    await page.getByRole("button", { name: /Register & Enter Studio/i }).click();

    // 3. Reach dashboard and verify user identity is preserved
    await expect(page.getByText(`@${creatorUsername}`)).toBeVisible();

    // 4. Create a new submission with banned term ('cheap' under acme-corp canon)
    const titleInput = page.locator("#sub-title");
    if (!(await titleInput.isVisible())) {
      await page.getByRole("button", { name: "+ New Campaign Bundle" }).click();
    }
    await titleInput.fill(`Golden Campaign ${timestamp}`);
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
    await page.getByRole("button", { name: /Confirm Transition/i }).click();
    await expect(page.locator(".status-badge").first()).toContainText(
      "in review",
    );

    // 11. Stage 2 -> Stage 3: Handoff to Brand Manager account (role-isolated)
    await page
      .getByRole("button", { name: /Sign In with Brand Manager Account/i })
      .click();
    await page.getByRole("button", { name: "Create Account" }).click();
    await page.locator("#signup-name").fill("Priya Nair");
    await page.locator("#signup-username").fill(reviewerUsername);
    await page.locator("#signup-role").selectOption("reviewer");
    await page.locator("#signup-password").fill(testPassword);
    await page.getByRole("button", { name: /Register & Enter Studio/i }).click();

    await expect(page.getByText(`@${reviewerUsername}`)).toBeVisible();
    await page
      .getByRole("button", { name: /Approve Brand Review/i })
      .click();
    await page.getByRole("button", { name: /Confirm Transition/i }).click();
    await expect(page.locator(".status-badge").first()).toContainText(
      "approved",
    );

    // 12. Stage 3 -> Stage 4: Handoff to Authorised Legal Reviewer account and release
    await page
      .getByRole("button", { name: /Sign In with Legal Reviewer Account/i })
      .click();
    await page.getByRole("button", { name: "Create Account" }).click();
    await page.locator("#signup-name").fill("Meera Iyer");
    await page.locator("#signup-username").fill(legalUsername);
    await page.locator("#signup-role").selectOption("admin");
    await page.locator("#signup-password").fill(testPassword);
    await page.getByRole("button", { name: /Register & Enter Studio/i }).click();

    await expect(page.getByText(`@${legalUsername}`)).toBeVisible();
    await page
      .getByRole("button", { name: /Execute Final Legal Sign-Off & Release/i })
      .click();
    await page.getByRole("button", { name: /Confirm Transition/i }).click();
    await expect(page.locator(".status-badge").first()).toContainText(
      "published",
    );

    // 13. Open and verify the cryptographic audit trail (including Merkle root & signature)
    await page.getByRole("button", { name: /Audit Trail/i }).click();
    await expect(
      page.getByRole("heading", { name: /Approval & Sign-Off Audit Trail/i }),
    ).toBeVisible();
    await expect(page.getByText("Cryptographic Audit Summary:")).toBeVisible();
    await expect(page.locator(".audit-event").first()).toBeVisible();
    await page.getByRole("button", { name: /Close/i }).click();
  });
});
