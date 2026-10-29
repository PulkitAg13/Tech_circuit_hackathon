import { test, expect } from '@playwright/test';

test.describe('CanonGate Golden Path E2E', () => {
  test('Full governance lifecycle: Creator fixes blockers -> Brand Approves -> Legal Approves -> Certificate Issued', async ({
    page,
  }) => {
    // 1. Open Public Home Page and verify live workbench & role gateway
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Pre-Publish Brand & Regulatory/i })
    ).toBeVisible();
    await expect(page.getByText('Workspace Role Gateway')).toBeVisible();

    // 2. Navigate to Login Page and sign in via Quick Role Switcher as Creator
    await page.goto('/login');
    await expect(page.getByText('CanonGate').first()).toBeVisible();
    await page.getByTestId('quick-login-creative_lead').click();

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByText('@creative_lead')).toBeVisible();

    // 3. Ensure New Campaign Bundle form is open
    const titleInput = page.getByPlaceholder('e.g., Q3 Lending Launch');
    if (!(await titleInput.isVisible())) {
      await page.getByRole('button', { name: /New Campaign Bundle/i }).click();
    }

    // 4. Create a new campaign submission with intentional violations
    await titleInput.fill('E2E Golden Campaign');
    await page.locator('select').first().selectOption('acme-corp');
    await page
      .getByPlaceholder(/Paste or write campaign text/i)
      .fill(
        'Acme Cloud guarantees 99.99% uptime SLA and is the #1 fastest platform on earth. Try our cheap enterprise tier today!'
      );

    await page.getByRole('button', { name: /Create & Run Scan/i }).click();

    // 5. Should navigate to Submission Detail Page and show BLOCKED status
    await expect(page).toHaveURL(/\/submissions\/(sub_|\d+)/);
    await expect(page.getByText('BLOCKED').first()).toBeVisible();

    // Verify Submit for Review button is disabled while blockers exist
    const submitForReviewBtn = page.getByTestId('submit-for-review-btn');
    await expect(submitForReviewBtn).toBeDisabled();

    // 6. Apply surgical fixes or edit artifact to clear blockers
    const editor = page.getByTestId('artifact-editor');
    await expect(editor).toBeVisible();
    await editor.fill(
      'Acme Cloud provides a 99.9% uptime SLA (Standard Enterprise Agreement) with cost-effective enterprise plans.'
    );

    await page.getByTestId('rescan-artifact-btn').click();

    // Wait for rescan to complete and blockers to drop to 0
    await expect(submitForReviewBtn).toBeEnabled({ timeout: 15000 });

    // 7. Creator submits for review -> status becomes IN_REVIEW
    await submitForReviewBtn.click();
    await expect(page.getByText('IN REVIEW').first()).toBeVisible();

    // 8. Switch role in-place to Brand Manager and approve
    await page.getByTestId('switch-role-brand_manager').click();
    await expect(page.getByText('@brand_manager')).toBeVisible();

    await page
      .getByPlaceholder(/Add rationale for audit trail/i)
      .fill('Brand tone and claims verified.');
    await page.getByTestId('decision-approve-btn').click();

    // Verify Brand Manager stage is marked APPROVED in progress bar
    await expect(page.getByText('1. Brand Manager')).toBeVisible();

    // 9. Switch role in-place to Legal Reviewer and approve
    await page.getByTestId('switch-role-legal_counsel').click();
    await expect(page.getByText('@legal_counsel')).toBeVisible();

    await page
      .getByPlaceholder(/Add rationale for audit trail/i)
      .fill('Legal compliance verified.');
    await page.getByTestId('decision-approve-btn').click();

    // 10. Status becomes APPROVED and Merkle Certificate button appears
    await expect(page.getByText('APPROVED').first()).toBeVisible();
    const viewCertBtn = page.getByTestId('view-certificate-btn');
    await expect(viewCertBtn).toBeVisible();

    // 11. Open Certificate Modal and verify cryptographic fields
    await viewCertBtn.click();
    await expect(page.getByTestId('certificate-modal')).toBeVisible();
    await expect(
      page.getByText('Cryptographic Compliance Certificate')
    ).toBeVisible();
    await expect(
      page.getByText('Merkle Findings Root (SHA-256)')
    ).toBeVisible();

    // Close modal
    await page.getByRole('button', { name: /Close/i }).click();
  });
});
