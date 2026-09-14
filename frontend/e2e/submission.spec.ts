import { test, expect } from '@playwright/test';

const testData = {
  rec_success: "11111111-1111-1111-1111-222222222222",
  rec_failure: "22222222-2222-2222-2222-222222222222",
  rec_unknown: "33333333-3333-3333-3333-222222222222",
  job_success: "11111111-1111-1111-1111-111111111111",
  job_failure: "22222222-2222-2222-2222-111111111111",
  job_unknown: "33333333-3333-3333-3333-111111111111"
};

test.describe('Application Review & Submission Flow', () => {

  test('Test A — successful flow (with SSE validation)', async ({ page, request }) => {
    page.on('console', msg => console.log(`[browser] ${msg.text()}`));
    page.on('requestfailed', request => console.log(`[network] Request failed: ${request.url()} - ${request.failure()?.errorText}`));
    // 1. Recommendation
    await page.goto('/recommendations');
    const card = page.locator(`text=Job ID: ${testData.job_success}`).locator('..').locator('..');
    
    // 2. Prepare
    await card.locator('text="Prepare Application"').click();

    // 3. Application Review & PREPARING
    await expect(page.locator('text="Preparing Application..."')).toBeVisible();
    
    // 4. SSE refresh to READY_FOR_REVIEW
    // Prove that task progress causes frontend to refresh organically
    await expect(page.locator('text="Review Application Data"')).toBeVisible({ timeout: 30000 });

    // 5. Inspect fields
    const approveBtn = page.locator('button', { hasText: 'Approve Application' });
    await expect(approveBtn).toBeDisabled();

    // Fill missing required fields
    const fieldInputs = page.locator('input[type="text"]');
    const count = await fieldInputs.count();
    for(let i=0; i<count; i++) {
        await fieldInputs.nth(i).fill('Test Value');
    }
    const textareas = page.locator('textarea');
    const taCount = await textareas.count();
    for(let i=0; i<taCount; i++) {
        await textareas.nth(i).fill('Test Value');
    }
    
    // Save to trigger validation refresh
    await page.click('button:has-text("Save Changes")');
    await expect(approveBtn).toBeEnabled();

    // 6. Approve -> APPROVED
    await approveBtn.click();
    await expect(page.locator('text="Application Approved"')).toBeVisible();

    // Verify submission does not happen automatically
    const submitBtn = page.locator('button', { hasText: 'Submit Application Now' });
    await expect(submitBtn).toBeVisible();
    await expect(submitBtn).toBeEnabled();

    // 7. Explicit Submit
    await submitBtn.click();
    
    // 8. SUBMITTING
    await expect(page.locator('text="Submitting Application..."')).toBeVisible();

    // 9. SUBMITTED (via SSE)
    await expect(page.locator('text="Application Submitted!"')).toBeVisible({ timeout: 30000 });
  });

  test('Test B — required fields blocking approval', async ({ page }) => {
    // Covered in Test A
  });

  test('Test E — submission failure', async ({ page }) => {
    await page.goto('/recommendations');
    const card = page.locator(`text=Job ID: ${testData.job_failure}`).locator('..').locator('..');
    await card.locator('text="Prepare Application"').click();
    
    await expect(page.locator('text="Review Application Data"')).toBeVisible({ timeout: 30000 });
    
    const fieldInputs = page.locator('input[type="text"]');
    const count = await fieldInputs.count();
    for(let i=0; i<count; i++) {
        await fieldInputs.nth(i).fill('Test Value');
    }
    await page.click('button:has-text("Save Changes")');

    await page.click('button:has-text("Approve Application")');
    await page.click('button:has-text("Submit Application Now")');
    
    await expect(page.locator('text="Submission Failed"')).toBeVisible({ timeout: 30000 });
  });

  test('Test F — uncertain submission', async ({ page, request }) => {
    await page.goto('/recommendations');
    const card = page.locator(`text=Job ID: ${testData.job_unknown}`).locator('..').locator('..');
    await card.locator('text="Prepare Application"').click();
    
    await expect(page.locator('text="Review Application Data"')).toBeVisible({ timeout: 30000 });
    
    const fieldInputs = page.locator('input[type="text"]');
    const count = await fieldInputs.count();
    for(let i=0; i<count; i++) {
        await fieldInputs.nth(i).fill('Test Value');
    }
    await page.click('button:has-text("Save Changes")');

    await page.click('button:has-text("Approve Application")');
    
    // Start listening to network to assert NO second submission request occurs
    let submitCount = 0;
    page.on('request', req => {
      if (req.url().includes('/submit') && req.method() === 'POST') {
        submitCount++;
      }
    });

    await page.click('button:has-text("Submit Application Now")');
    
    await expect(page.locator('text="Submission Outcome Uncertain"')).toBeVisible({ timeout: 30000 });
    
    // Assert no auto-retry occurs
    await expect(page.locator('button:has-text("Submit Application Now")')).not.toBeVisible();
    expect(submitCount).toBe(1);
  });

  test('Test G — ownership isolation', async ({ page, request }) => {
    // Navigate to a UUID that does not exist or belongs to someone else
    await page.goto('/applications/00000000-0000-0000-0000-000000000000');
    // Using standard API error handling, it should fail to load
    await expect(page.locator('text="Application not found"')).toBeVisible();
  });

});

