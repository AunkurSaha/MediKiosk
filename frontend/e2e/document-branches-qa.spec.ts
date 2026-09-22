import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

for (const answer of ['No', 'Not sure'] as const) {
  test(`prescription confirmation ${answer} does not falsely optimize history`, async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: 'Use Demo Patient' }).click();
    await page.getByRole('button', { name: /English/ }).click();
    await page.getByRole('button', { name: /Continue/ }).click();
    await page.locator('input[type="checkbox"]').first().check();
    await page.getByTestId('consent-document-checkbox').check();
    await page.getByRole('button', { name: /Start/ }).click();
    await page.getByRole('button', { name: 'Fever', exact: true }).click();
    await page.getByLabel('Answer').fill('38');
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.getByRole('button', { name: 'No', exact: true }).click();
    await page.getByRole('button', { name: 'Find a suitable facility' }).click();
    await page.getByLabel('Locality').fill('Kolkata');
    await page.getByRole('button', { name: 'Search by locality' }).click();
    await page.getByRole('button', { name: 'Select facility' }).first().click();
    await page
      .locator('article')
      .filter({ hasText: 'Dr. Ishan Gupta' })
      .getByRole('button', { name: 'Select Doctor' })
      .click();
    const prescription = await readFile('../ai/document_fixtures/metformin_prescription.png');
    await page
      .getByTestId('document-file-input')
      .setInputFiles({
        name: 'synthetic-metformin-prescription.png',
        mimeType: 'image/png',
        buffer: prescription,
      });
    await page
      .getByRole('textbox', { name: 'Your answer' })
      .fill('Fever since yesterday; no breathing difficulty.');
    await page.getByRole('button', { name: /Save and continue/ }).click();
    await page.getByLabel(answer, { exact: true }).check();
    await page.getByRole('button', { name: /Save and continue/ }).click();
    await expect(page.getByTestId('medication-history-optimized')).toHaveCount(0);
    await expect(page.locator('.question-header h1')).toBeVisible();
    await page.reload();
    await expect(page.getByTestId('medication-history-optimized')).toHaveCount(0);
    await expect(page.locator('.question-header h1')).toBeVisible();
  });
}
