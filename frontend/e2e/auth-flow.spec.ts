import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test.describe('Mobile Phone Number + OTP Authentication Flow', () => {
  test('Complete phone login, OTP verification, session access, and logout protection', async ({
    page,
    request,
  }) => {
    test.setTimeout(60000);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.setViewportSize({ width: 1360, height: 900 });
    await mkdir('../.runtime/screenshots', { recursive: true });

    // 1. Navigate to /login directly
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();
    await expect(page.getByText('Patient Login', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Mobile Number')).toBeVisible();

    // 2. Enter synthetic test phone number
    const testPhone = '9876543210';
    await page.getByLabel('Mobile Number').fill(testPhone);

    // 3. Request OTP
    await page.getByRole('button', { name: 'Send OTP' }).click();

    // 4. Verify OTP screen renders
    await expect(page.getByText('+91******3210')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Verify OTP' })).toBeVisible();

    // 5. Retrieve test OTP from development test sink
    const devRes = await request.get(`/api/auth/dev/last-otp?phone_number=%2B91${testPhone}`);
    expect(devRes.ok()).toBeTruthy();
    const { otp } = await devRes.json();
    expect(otp).toHaveLength(6);

    // 6. Enter OTP digits into the 6 input boxes
    for (let i = 0; i < 6; i++) {
      await page.getByLabel(`Digit ${i + 1}`).fill(otp[i]);
    }

    // 7. Verify OTP
    await page.getByRole('button', { name: 'Verify OTP' }).click();

    // 8. Confirms authenticated redirect to patient kiosk flow
    await expect(page).toHaveURL(/\/kiosk\/language/);
    await expect(page.getByRole('heading', { name: /Choose your language|A little preparation/ })).toBeVisible();

    // 9. Confirm header displays authenticated user badge and Logout button
    await expect(page.getByText(/\+91\*{6}3210/)).toBeVisible();
    const logoutBtn = page.getByRole('button', { name: 'Logout' });
    await expect(logoutBtn).toBeVisible();

    // Capture screenshot of authenticated patient view
    await page.screenshot({
      path: '../.runtime/screenshots/auth-patient-kiosk.png',
      fullPage: true,
    });

    // 10. Click Logout
    await logoutBtn.click();

    // 11. Confirm redirected back to /login
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();
    await expect(page.getByText('Patient Login', { exact: true })).toBeVisible();

    // Capture screenshot of login screen
    await page.screenshot({
      path: '../.runtime/screenshots/auth-logged-out.png',
      fullPage: true,
    });

    // 12. Confirm protected route is inaccessible after logout
    await page.goto('/kiosk/language');
    // Must be redirected to /login because user is logged out
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();
    await expect(page.getByText('Patient Login', { exact: true })).toBeVisible();

    expect(errors).toEqual([]);
  });
});
