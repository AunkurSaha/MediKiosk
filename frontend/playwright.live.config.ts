import { defineConfig } from '@playwright/test';
import base from './playwright.config';

// Explicit separate command; reads only synthetic records created by the live evaluator.
export default defineConfig({ ...base, globalSetup: undefined, testDir: './live', workers: 1 });
