import { test, expect } from '@playwright/test';

test.describe('Unit 3: Create Emergency Alert via Patient UI', () => {
  test('should trigger RF-CHEST-001 alert via patient UI and verify persistence', async ({
    page,
  }) => {
    test.setTimeout(120000);

    // 1. Start at kiosk language selection
    await page.goto('/kiosk/language');

    // 2. Use Demo Patient (English)
    await page.getByRole('button', { name: /English/ }).click();

    // 3. Demographics - using demo patient data from sessionStorage
    await page.getByLabel('Patient name').fill('Demo Patient');
    await page.getByLabel('Gender').selectOption('female');
    await page.getByLabel('Age (years)').fill('42');
    await page.getByLabel('Height (cm)').fill('162');
    await page.getByLabel('Weight (kg)').fill('64');
    await page.getByLabel('Hospital token').fill('DEMO-FEVER'); // Demo patient token
    await page.getByRole('button', { name: 'Continue', exact: true }).click();

    // 4. Consent
    await page.getByRole('checkbox', { name: /agree to store/i }).check();
    await page.getByRole('button', { name: 'Start the interview', exact: true }).click();

    // 5. Start intake - Select chest discomfort
    await page.getByRole('button', { name: 'Chest discomfort', exact: true }).click();

    // 6. Chest discomfort - severity 9
    await page.getByLabel('How severe is the chest discomfort right now, from 0 to 10?').fill('9');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // 7. Breathlessness No
    await page.getByLabel('Are you short of breath now?').getByLabel('No', { exact: true }).check();
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // 8. Radiation Yes
    await page.getByLabel('Does the discomfort spread to your arm, jaw, back, or another area?').getByLabel('Yes', { exact: true }).check();
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // 9. Radiation site (required follow-up question)
    await page.getByLabel('Where does it spread?').fill('Left arm');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // 10. Confirm that RF-CHEST-001 is triggered
    // Look for the emergency advisory
    const advisory = page.getByTestId('kiosk-safety-advisory');
    await expect(advisory).toBeVisible();
    await expect(advisory).toContainText('Potential emergency symptoms detected');
    await expect(advisory).toContainText('Immediate clinical assessment recommended');

    // 11. Verify that the alert persists in the backend
    // Continue to find care facility to complete the flow
    await page.getByRole('button', { name: 'Find emergency-capable facilities' }).click();

    // Select a facility (first available)
    await page.getByRole('button', { name: /Select/ }).first().click();

    // Complete the interview
    await page.getByRole('button', { name: 'Start interview', exact: true }).click();

    // Answer a few interview questions to reach completion
    await page.getByLabel('When did the chest discomfort start?').fill('2 hours ago');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    await page.getByLabel('How would you describe the chest discomfort?').fill('Heavy pressure');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    await page.getByLabel('Is the discomfort constant or intermittent?').getByLabel('Constant', { exact: true }).check();
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // Complete the intake
    await page.getByRole('button', { name: 'Complete intake', exact: true }).click();

    // Wait for completion page
    await expect(page.getByRole('heading', { name: /Your pre-consultation intake is ready/ })).toBeVisible();

    // 12. Verify alert persistence via API
    // Get the alerts for this session
    const alertsResponse = await page.request.get('/api/triage/alerts');
    expect(alertsResponse.ok()).toBeTruthy();

    const alertsData = await alertsResponse.json();
    expect(alertsData.items.length).toBeGreaterThan(0);

    // Find the RF-CHEST-001 alert
    const rfChestAlert = alertsData.items.find(
      (alert: any) => alert.triggered_rule_ids.includes('RF-CHEST-001')
    );

    expect(rfChestAlert).toBeDefined();
    expect(rfChestAlert?.priority).toBe('emergency');
    expect(rfChestAlert?.rule_id).toBe('RF-CHEST-001');

    // Alternatively, verify via direct database query (optional)
    // We could query the e2e.sqlite database directly, but API verification is sufficient

    console.log('✓ RF-CHEST-001 alert successfully triggered and persisted');
  });
});