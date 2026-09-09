import { test, expect } from '@playwright/test';

test.describe('Phase 5 — Deterministic Red-Flag Safety & Staff Triage Dashboard', () => {
  test('emergency red-flag triggers kiosk advisory, triage dashboard card, staff acknowledgement, and doctor alert visibility', async ({
    page,
  }) => {
    test.setTimeout(120000);
    const token = 'RF-TEST-' + Date.now();

    // 1. Kiosk Patient Intake & Emergency Trigger
    await page.goto('/kiosk/language');
    await page.getByRole('button', { name: /English/ }).click();
    await page.getByLabel('Patient name').fill('Emergency Test Patient');
    await page.getByLabel('Hospital token').fill(token);
    await page.getByRole('button', { name: 'Continue', exact: true }).click();

    await page.getByRole('checkbox', { name: /agree to store/i }).check();
    await page.getByRole('button', { name: 'Start intake', exact: true }).click();

    // Select chest pain complaint flow
    await page.getByRole('button', { name: 'Chest pain', exact: true }).click();

    // Answer questions until hpi.radiation and hpi.severity
    // chief_complaint.description
    await page.getByLabel('Your answer', { exact: true }).fill('Severe chest crushing');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // hpi.onset
    await page.getByLabel('Your answer', { exact: true }).fill('2');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // hpi.site
    await page.getByLabel('Your answer', { exact: true }).fill('Center of chest');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // hpi.character
    await page.getByLabel('Your answer', { exact: true }).fill('Heavy pressure');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // hpi.radiation -> Yes (triggers condition for RF-CHEST-001)
    await page.getByLabel('Yes', { exact: true }).check();
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // hpi.radiation_site
    await page.getByLabel('Your answer', { exact: true }).fill('Left arm and jaw');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // hpi.timing
    await page.getByLabel('Constant', { exact: true }).check();
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // hpi.severity -> 9 (triggers RF-CHEST-001: severity >= 8 AND radiation == true)
    await page.getByLabel('Your answer', { exact: true }).fill('9');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // Verify Calm Kiosk Safety Advisory is displayed prominently
    const advisory = page.getByTestId('kiosk-safety-advisory');
    await expect(advisory).toBeVisible();
    await expect(advisory).toContainText('Staff Assessment Recommended');
    await expect(advisory).toContainText('Potential emergency symptoms were detected');
    await expect(advisory).toContainText('Medical staff have been notified');

    // 2. Staff Triage Dashboard Verification
    await page.goto('/triage');
    await expect(page.getByRole('heading', { name: /Staff Triage & Safety Dashboard/i })).toBeVisible();

    // Locate the alert card corresponding to our token
    const tokenBadge = page.locator('.patient-token-badge', { hasText: token });
    await expect(tokenBadge).toBeVisible();

    const alertCard = page.locator('.alert-card', { has: tokenBadge });
    await expect(alertCard).toBeVisible();
    await expect(alertCard.locator('.priority-badge.emergency')).toContainText('EMERGENCY');
    await expect(alertCard).toContainText('RF-CHEST-001');
    await expect(alertCard).toContainText('Emergency Test Patient');

    // Staff Acknowledges the Alert
    await alertCard.getByRole('button', { name: 'Acknowledge Alert' }).click();

    const staffInput = alertCard.locator('input[placeholder*="Staff member name"]');
    await staffInput.fill('Nurse Station Alpha');

    const noteInput = alertCard.locator('input[placeholder*="Action taken note"]');
    await noteInput.fill('Patient moved to resuscitation bay for immediate ECG');

    await alertCard.getByRole('button', { name: 'Confirm Acknowledgement' }).click();

    // Verify card updates to acknowledged
    await expect(alertCard.locator('.status-badge')).toContainText('Acknowledged');
    await expect(alertCard).toContainText('Nurse Station Alpha');
    await expect(alertCard).toContainText('Patient moved to resuscitation bay');

    // 3. Doctor Workspace Alert Visibility
    await page.goto('/doctor');
    const patientRow = page.getByRole('link', { name: new RegExp(token) });
    await expect(patientRow).toBeVisible();
    await patientRow.click();

    // Check doctor alerts banner
    const docBanner = page.getByTestId('doctor-alerts-banner');
    await expect(docBanner).toBeVisible();
    await expect(docBanner).toContainText('Safety Screening Alerts');
    await expect(docBanner).toContainText('EMERGENCY');
    await expect(docBanner).toContainText('RF-CHEST-001');
    await expect(docBanner).toContainText('Nurse Station Alpha');
  });

  test('non-emergency session does not display emergency advisory', async ({ page }) => {
    test.setTimeout(60000);
    const token = 'NORM-' + Date.now();

    await page.goto('/kiosk/language');
    await page.getByRole('button', { name: /English/ }).click();
    await page.getByLabel('Patient name').fill('Mild Patient');
    await page.getByLabel('Hospital token').fill(token);
    await page.getByRole('button', { name: 'Continue', exact: true }).click();

    await page.getByRole('checkbox', { name: /agree to store/i }).check();
    await page.getByRole('button', { name: 'Start intake', exact: true }).click();

    await page.getByRole('button', { name: 'Chest pain', exact: true }).click();

    // Chief complaint
    await page.getByLabel('Your answer', { exact: true }).fill('Mild ache');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // Verify kiosk advisory is NOT visible
    const advisory = page.getByTestId('kiosk-safety-advisory');
    await expect(advisory).not.toBeVisible();
  });
});
