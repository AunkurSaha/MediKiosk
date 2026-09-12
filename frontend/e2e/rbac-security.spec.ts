import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test.describe('Role-Based Access Control (RBAC) Hardened Security Journeys', () => {
  test('Strict role separation: Patient blocked from Doctor & Triage, Doctor blocked from Triage, Triage blocked from Doctor', async ({
    page,
    request,
  }) => {
    test.setTimeout(90000);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.setViewportSize({ width: 1360, height: 900 });
    await mkdir('../.runtime/screenshots', { recursive: true });

    // =========================================================================
    // 1. PATIENT FLOW: Phone OTP Login & Hardened Route / API Isolation
    // =========================================================================
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();

    // Unique phone number for this test run
    const phone = `97${String(Date.now()).slice(-8)}`;
    const maskedPhone = `+91******${phone.slice(-4)}`;

    await page.getByLabel('Mobile Number').fill(phone);
    await page.getByRole('button', { name: 'Send OTP' }).click();

    await expect(page.getByText(maskedPhone)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Verify OTP' })).toBeVisible();

    // Retrieve OTP from dev sink
    const devRes = await request.get(`/api/auth/dev/last-otp?phone_number=%2B91${phone}`);
    expect(devRes.ok()).toBeTruthy();
    const { otp } = await devRes.json();

    for (let i = 0; i < 6; i++) {
      await page.getByLabel(`Digit ${i + 1}`).fill(otp[i]);
    }
    await page.getByRole('button', { name: 'Verify OTP' }).click();

    // Confirm patient lands on kiosk
    await expect(page).toHaveURL(/\/kiosk\/language/);

    // Verify navigation bar shows ONLY patient links
    const nav = page.getByRole('navigation', { name: 'MediKiosk' });
    await expect(nav.getByRole('link', { name: 'Patient intake' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Doctor workspace' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: 'Triage' })).toHaveCount(0);

    // --- Attempt 1: Direct URL navigation to /doctor as patient ---
    await page.goto('/doctor');
    await expect(page.getByRole('heading', { name: 'Doctor Access Required' })).toBeVisible();
    // Verify NO doctor workspace data or elements are rendered
    await expect(page.getByRole('heading', { name: 'Ready to review' })).toHaveCount(0);
    await expect(page.getByText('Consultation preparation')).toHaveCount(0);
    await expect(page.getByText(/patient mobile verification cannot grant doctor privileges/i)).toBeVisible();

    // Test browser refresh while authenticated as patient: must REMAIN blocked!
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Doctor Access Required' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Ready to review' })).toHaveCount(0);

    // Screenshot: Patient blocked from Doctor
    await page.screenshot({
      path: '../.runtime/screenshots/rbac-01-patient-blocked-from-doctor.png',
      fullPage: true,
    });

    // --- Attempt 2: Direct URL navigation to /triage as patient ---
    await page.goto('/triage');
    await expect(page.getByRole('heading', { name: 'Triage Access Required' })).toBeVisible();
    // Verify NO triage dashboard elements or alerts table are rendered
    await expect(page.getByRole('heading', { name: /Staff Triage & Safety Dashboard/i })).toHaveCount(0);
    await expect(page.getByText(/Triage Operational Board/i)).toHaveCount(0);

    // Test browser refresh while on /triage as patient: must REMAIN blocked!
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Triage Access Required' })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Staff Triage & Safety Dashboard/i })).toHaveCount(0);

    // Screenshot: Patient blocked from Triage
    await page.screenshot({
      path: '../.runtime/screenshots/rbac-02-patient-blocked-from-triage.png',
      fullPage: true,
    });

    // --- Verify backend API level 403 Forbidden for patient ---
    const apiDocRes = await page.evaluate(async () => {
      const res = await fetch('/api/doctor/sessions', {
        headers: { Accept: 'application/json' },
      });
      return { status: res.status, json: await res.json() };
    });
    expect(apiDocRes.status).toBe(403);
    expect(apiDocRes.json.error?.code).toBe('FORBIDDEN');

    const apiTriageRes = await page.evaluate(async () => {
      const res = await fetch('/api/triage/alerts', {
        headers: { Accept: 'application/json' },
      });
      return { status: res.status, json: await res.json() };
    });
    expect(apiTriageRes.status).toBe(403);
    expect(apiTriageRes.json.error?.code).toBe('FORBIDDEN');

    // Logout patient
    await page.goto('/kiosk/language');
    await page.getByRole('button', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login/);

    // =========================================================================
    // 2. DOCTOR FLOW: Doctor Login & Doctor Workspace Authorization
    // =========================================================================
    await page.getByRole('button', { name: 'Quick Demo Doctor Login' }).click();
    await expect(page).toHaveURL(/\/doctor/);
    await expect(page.getByRole('heading', { name: 'Ready to review' })).toBeVisible();

    // Verify doctor nav bar
    const docNav = page.getByRole('navigation', { name: 'MediKiosk' });
    await expect(docNav.getByRole('link', { name: 'Doctor workspace' })).toBeVisible();
    await expect(docNav.getByRole('link', { name: 'Patient intake' })).toHaveCount(0);
    await expect(docNav.getByRole('link', { name: 'Triage' })).toHaveCount(0);

    // Screenshot: Doctor workspace
    await page.screenshot({
      path: '../.runtime/screenshots/rbac-03-doctor-workspace.png',
      fullPage: true,
    });

    // Doctor attempting /triage is BLOCKED
    await page.goto('/triage');
    await expect(page.getByRole('heading', { name: 'Triage Access Required' })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Staff Triage & Safety Dashboard/i })).toHaveCount(0);

    // Logout doctor
    await page.goto('/doctor');
    await page.getByRole('button', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login/);

    // =========================================================================
    // 3. TRIAGE FLOW: Triage Login & Alert Dashboard Authorization
    // =========================================================================
    await page.getByRole('button', { name: 'Quick Triage Demo' }).click();
    await expect(page).toHaveURL(/\/triage/);
    await expect(page.getByRole('heading', { name: /Staff Triage & Safety Dashboard/i })).toBeVisible();

    // Verify triage nav bar
    const triageNav = page.getByRole('navigation', { name: 'MediKiosk' });
    await expect(triageNav.getByRole('link', { name: 'Triage' })).toBeVisible();
    await expect(triageNav.getByRole('link', { name: 'Doctor workspace' })).toHaveCount(0);
    await expect(triageNav.getByRole('link', { name: 'Patient intake' })).toHaveCount(0);

    // Screenshot: Triage dashboard
    await page.screenshot({
      path: '../.runtime/screenshots/rbac-04-triage-dashboard.png',
      fullPage: true,
    });

    // Triage user attempting /doctor is BLOCKED
    await page.goto('/doctor');
    await expect(page.getByRole('heading', { name: 'Doctor Access Required' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Ready to review' })).toHaveCount(0);

    // Triage user attempting doctor API receives 403
    const triageApiDocRes = await page.evaluate(async () => {
      const res = await fetch('/api/doctor/sessions', {
        headers: { Accept: 'application/json' },
      });
      return { status: res.status, json: await res.json() };
    });
    expect(triageApiDocRes.status).toBe(403);
    expect(triageApiDocRes.json.error?.code).toBe('FORBIDDEN');

    // Clean logout
    await page.goto('/triage');
    await page.getByRole('button', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login/);

    expect(errors).toEqual([]);
  });
});
