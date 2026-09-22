import { expect, test } from '@playwright/test';

test('captures the polished patient, triage, and doctor recording surfaces', async ({
  browser,
}) => {
  test.setTimeout(180_000);

  for (const surface of [
    {
      role: 'patient',
      path: '/kiosk/language',
      heading: /A little preparation/i,
      screenshot: 'patient-intake-surface.png',
    },
    {
      role: 'triage',
      path: '/triage',
      heading: /Staff Triage/i,
      screenshot: 'triage-surface.png',
    },
    {
      role: 'doctor',
      path: '/doctor',
      heading: /Ready to review/i,
      screenshot: 'doctor-workspace-surface.png',
    },
  ] as const) {
    const context = await browser.newContext({
      baseURL: 'http://127.0.0.1:5175',
      viewport: { width: 1920, height: 1080 },
    });
    const page = await context.newPage();
    const login = await page.request.post('/api/auth/demo-login', {
      data: { role: surface.role },
    });
    expect(login.ok(), await login.text()).toBeTruthy();
    await page.goto(surface.path);
    if (surface.role === 'triage') {
      await page
        .getByRole('button', { name: /MediKiosk City Hospital/i })
        .click({ timeout: 60_000 });
    }
    await expect(page.getByRole('heading', { name: surface.heading }).first()).toBeVisible({
      timeout: 60_000,
    });
    if (surface.role === 'triage') {
      await expect(page.getByRole('status').filter({ hasText: /Loading alerts/i })).toBeHidden({
        timeout: 60_000,
      });
    }
    if (surface.role === 'doctor') {
      await expect(page.getByRole('status').filter({ hasText: /Loading/i })).toBeHidden({
        timeout: 60_000,
      });
    }
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: `../.runtime/screenshots/${surface.screenshot}`,
      fullPage: true,
    });
    await context.close();
  }
});
