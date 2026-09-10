import { request } from '@playwright/test';

export default async function requireMock() {
  const client = await request.newContext({ baseURL: 'http://127.0.0.1:5175' });
  try {
    const response = await client.get('/api/config');
    if (!response.ok() || (await response.json()).normalization_provider !== 'mock') {
      throw new Error(
        'Offline E2E requires an explicitly mock backend. Stop dev services, then run scripts/start-dev.ps1 -NormalizationProvider mock. The live evaluator uses its own process.',
      );
    }
  } finally {
    await client.dispose();
  }
}
