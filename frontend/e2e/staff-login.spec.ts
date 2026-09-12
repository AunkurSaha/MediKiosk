import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test.describe('Staff & Specialist Unified Login, OTP & Registration Flow', () => {
  test('Complete journey: Patient switcher -> Staff Sign Up -> Staff Phone OTP Login -> Staff Password Login -> Return to Kiosk', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.setViewportSize({ width: 1360, height: 900 });
    await mkdir('../.runtime/screenshots', { recursive: true });

    // 1. Visit Patient Login page
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();

    // 2. Verify switcher option to specialist / staff portal
    const switcherTitle = page.getByText(/Clinical Specialist & Staff Portal/i);
    await expect(switcherTitle).toBeVisible();

    const switchLink = page.getByRole('link', { name: /Staff Password Login →/i });
    await expect(switchLink).toBeVisible();
    await switchLink.click();

    // 3. Lands on unified staff portal
    await expect(page).toHaveURL(/\/staff\/login/);
    await expect(page.getByText(/Hospital Staff & Specialist Portal/i)).toBeVisible();

    // Verify all 3 tabs are present
    const passwordTab = page.getByRole('button', { name: /Password Login/i });
    const otpTab = page.getByRole('button', { name: /Phone OTP/i });
    const signUpTab = page.getByRole('button', { name: /Sign Up/i });

    await expect(passwordTab).toBeVisible();
    await expect(otpTab).toBeVisible();
    await expect(signUpTab).toBeVisible();

    // =========================================================================
    // 4. Test TAB 3: Staff Registration / Sign Up
    // =========================================================================
    await signUpTab.click();

    const uniquePhone = `98${String(Date.now()).slice(-8)}`;

    await page.getByLabel(/Full Name/i).fill('Dr. Registered Clinician');
    await page.getByRole('button', { name: /Doctor \(Clinician\)/i }).click();
    await page.getByLabel(/Mobile Number/i).fill(uniquePhone);
    await page.getByLabel(/Official Email/i).fill(`reg.doc.${uniquePhone}@hospital.invalid`);
    await page.getByLabel(/Create Password/i).fill('Clinician@123');

    await page.getByRole('button', { name: /Create Staff Account & Sign In/i }).click();

    // Newly registered doctor lands in /doctor
    await expect(page).toHaveURL(/\/doctor/);
    await expect(page.getByRole('heading', { name: 'Ready to review' })).toBeVisible();

    // CRITICAL REQUIREMENT: Verify doctor navbar does NOT have "Patient intake"!
    const docNav = page.getByRole('navigation', { name: 'MediKiosk' });
    await expect(docNav.getByRole('link', { name: 'Doctor workspace' })).toBeVisible();
    await expect(docNav.getByRole('link', { name: /Patient intake/i })).toHaveCount(0);

    // Direct navigation by doctor to /kiosk/language must be blocked!
    await page.goto('/kiosk/language');
    await expect(page.getByText(/Patient Intake Access Only/i)).toBeVisible();
    await expect(page.getByText(/The kiosk intake journey is reserved for patients/i)).toBeVisible();

    await page.screenshot({
      path: '../.runtime/screenshots/staff-01-doctor-isolated-from-kiosk.png',
      fullPage: true,
    });

    // Return to doctor workspace and logout
    await page.goto('/doctor');
    await docNav.getByRole('button', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login/);

    // =========================================================================
    // 5. Test TAB 2: Staff Phone OTP Login (Using newly registered staff phone)
    // =========================================================================
    await page.getByRole('link', { name: /Staff Password Login →/i }).click();
    await expect(page).toHaveURL(/\/staff\/login/);

    await page.getByRole('button', { name: /Phone OTP/i }).click();

    const otpPhoneInput = page.getByLabel(/Registered Staff Mobile Number/i);
    await expect(otpPhoneInput).toBeVisible();

    // Fill the newly registered staff phone number
    await otpPhoneInput.fill(uniquePhone);

    // Request Staff OTP
    await page.getByRole('button', { name: /Send Staff OTP/i }).click();
    await expect(page.getByText(/Enter 6-digit Code/i)).toBeVisible();

    // Retrieve OTP from dev sink
    const devOtpRes = await request.get(`/api/auth/dev/last-otp?phone_number=%2B91${uniquePhone}`);
    expect(devOtpRes.ok()).toBeTruthy();
    const { otp: staffOtp } = await devOtpRes.json();

    for (let i = 0; i < 6; i++) {
      await page.getByLabel(`Staff OTP Digit ${i + 1}`).fill(staffOtp[i]);
    }

    await page.getByRole('button', { name: /Verify & Enter Workspace/i }).click();

    // Doctor redirected to /doctor via OTP
    await expect(page).toHaveURL(/\/doctor/);
    await expect(page.getByRole('heading', { name: 'Ready to review' })).toBeVisible();

    await page.screenshot({
      path: '../.runtime/screenshots/staff-02-staff-otp-logged-in.png',
      fullPage: true,
    });

    // Logout
    await docNav.getByRole('button', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login/);

    // =========================================================================
    // 6. Test TAB 1: Password Login (Triage Quick Fill)
    // =========================================================================
    await page.getByRole('link', { name: /Staff Password Login →/i }).click();
    await expect(page).toHaveURL(/\/staff\/login/);

    const idInput = page.getByLabel(/Phone Number or Staff ID/i);
    const passInput = page.getByLabel(/^Password$/i);
    await expect(idInput).toBeVisible();
    await expect(passInput).toBeVisible();

    const triageQuickFill = page.getByRole('button', { name: /Triage:.*Sister Priya/i });
    await expect(triageQuickFill).toBeVisible();
    await triageQuickFill.click();

    await expect(idInput).toHaveValue('9876500002');
    await expect(passInput).toHaveValue('Triage@123');

    await page.getByRole('button', { name: /Sign In to Staff Workspace/i }).click();

    // Triage redirected to /triage
    await expect(page).toHaveURL(/\/triage/);
    await expect(page.getByRole('heading', { name: /Staff Triage & Safety Dashboard/i })).toBeVisible();

    const triageNav = page.getByRole('navigation', { name: 'MediKiosk' });
    await expect(triageNav.getByRole('link', { name: 'Triage' })).toBeVisible();
    await expect(triageNav.getByRole('link', { name: /Patient intake/i })).toHaveCount(0);

    await page.screenshot({
      path: '../.runtime/screenshots/staff-03-triage-dashboard.png',
      fullPage: true,
    });

    // Logout triage
    await triageNav.getByRole('button', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login/);

    // =========================================================================
    // 7. Test Return Switcher: /staff/login -> /login
    // =========================================================================
    await page.goto('/staff/login');
    const returnLink = page.getByRole('link', { name: /Switch to Patient Kiosk Intake/i });
    await expect(returnLink).toBeVisible();
    await returnLink.click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();

    expect(errors).toEqual([]);
  });
});
