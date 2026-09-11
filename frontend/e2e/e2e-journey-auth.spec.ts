import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test.describe('MediKiosk Authenticated End-to-End User Journey', () => {
  test('Complete journey: Login -> OTP -> Kiosk -> Showcase -> Document & Voice -> Doctor Review -> Logout', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.setViewportSize({ width: 1360, height: 900 });
    await mkdir('../.runtime/screenshots', { recursive: true });

    // Step 1: Start unauthenticated at /login
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();
    await expect(page.getByText('Patient Login', { exact: true })).toBeVisible();

    // Step 2: Enter Indian mobile number (+91)
    const phone = '9876543210';
    await page.getByLabel('Mobile Number').fill(phone);
    await page.getByRole('button', { name: 'Send OTP' }).click();

    // Step 3: Verify OTP transition
    await expect(page.getByText('+91******3210')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Verify OTP' })).toBeVisible();

    // Step 4: Fetch OTP from test sink
    const devRes = await request.get(`/api/auth/dev/last-otp?phone_number=%2B91${phone}`);
    expect(devRes.ok()).toBeTruthy();
    const { otp } = await devRes.json();
    expect(otp).toHaveLength(6);

    // Step 5: Fill digits & submit
    for (let i = 0; i < 6; i++) {
      await page.getByLabel(`Digit ${i + 1}`).fill(otp[i]);
    }
    await page.getByRole('button', { name: 'Verify OTP' }).click();

    // Step 6: Authenticated redirect to /kiosk/language
    await expect(page).toHaveURL(/\/kiosk\/language/);
    await expect(page.getByText(/\+91\*{6}3210/)).toBeVisible();

    // Screenshot: Authenticated kiosk landing
    await page.screenshot({
      path: '../.runtime/screenshots/journey-01-kiosk-landing.png',
      fullPage: true,
    });

    // Step 7: Load showcase patient (bilingual Bengali/English cardiac case)
    const showcaseBtn = page.getByTestId('kiosk-load-showcase-btn');
    await expect(showcaseBtn).toBeVisible();
    await showcaseBtn.click();

    // Step 8: Intake completes and navigates to complete screen
    await expect(page).toHaveURL(/\/kiosk\/complete$/);
    await expect(page.getByRole('heading', { name: 'চিকিৎসকের পর্যালোচনার জন্য প্রস্তুত' })).toBeVisible();
    await expect(page.getByText('T-SHOWCASE-101')).toBeVisible();

    // Screenshot: Completed intake
    await page.screenshot({
      path: '../.runtime/screenshots/journey-02-intake-completed.png',
      fullPage: true,
    });

    // Step 9: Doctor Review Workspace
    await page.goto('/doctor');
    const patientRow = page.locator('.session-card').filter({ hasText: 'সুমিতা শর্মা' });
    await expect(patientRow).toBeVisible();
    await patientRow.click();

    // Step 10: Verify Doctor Review clinical screen details
    await expect(page.getByRole('heading', { name: 'সুমিতা শর্মা' })).toBeVisible();
    await expect(page.getByTestId('doctor-alerts-banner')).toContainText('RF-CHEST-001');
    await expect(page.getByTestId('summary-workspace')).toBeVisible();
    await expect(page.getByTestId('document-viewer-panel')).toBeVisible();

    // Screenshot: Doctor review workspace
    await page.screenshot({
      path: '../.runtime/screenshots/journey-03-doctor-workspace.png',
      fullPage: true,
    });

    // Step 11: Confirm Clinical Summary
    const confirmBtn = page.getByRole('button', { name: /Confirm Summary|নিশ্চিত করুন/ });
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await expect(page.getByText(/Summary Confirmed|Confirmed/i)).toBeVisible();
    }

    // Step 12: Logout
    const logoutBtn = page.getByRole('button', { name: 'Logout' });
    await expect(logoutBtn).toBeVisible();
    await logoutBtn.click();

    // Step 13: Verify redirect to login and session cleared
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText('Patient Login', { exact: true })).toBeVisible();

    // Screenshot: Clean logout
    await page.screenshot({
      path: '../.runtime/screenshots/journey-04-logged-out.png',
      fullPage: true,
    });

    expect(errors).toEqual([]);
  });
});
