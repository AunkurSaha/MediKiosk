import { expect, test } from '@playwright/test';

test('patient selects same-hospital shortest-queue doctor and assignment isolates workspace', async ({ page }) => {
  const phone = `98${Date.now().toString().slice(-8)}`;
  await page.goto('/login');
  await page.getByLabel('Mobile Number').fill(phone);
  await page.getByRole('button', { name: 'Send OTP' }).click();
  await page.getByRole('button', { name: 'Fill Test OTP' }).click();
  await page.getByRole('button', { name: 'Verify OTP' }).click();
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByLabel('Patient name').fill('Routing Journey Patient');
  await page.getByLabel('Hospital token').fill(`ROUTE-${Date.now()}`);
  await page.getByRole('button', { name: 'Continue' }).click();

  await expect(page.getByRole('heading', { name: 'Which hospital are you visiting today?' })).toBeVisible();
  await page.getByRole('button', { name: /MediKiosk City Hospital/ }).click();
  await page.getByRole('checkbox', { name: 'I agree to store my answers' }).check();
  await page.getByRole('button', { name: 'Start the interview' }).click();
  await page.getByRole('button', { name: /Chest pain/i }).click();

  const doctors = page.getByTestId('doctor-match-list').locator('article');
  await expect(doctors.first()).toContainText(/patient(s)? waiting/);
  await expect(doctors.first()).toContainText('Recommended');
  await expect(page.getByText('Dr. Mira Roy')).toHaveCount(0);
  await doctors.first().getByRole('button', { name: 'Choose' }).click();
  await expect(page.getByRole('heading', { name: /What brings you|describe/i })).toBeVisible();
});
