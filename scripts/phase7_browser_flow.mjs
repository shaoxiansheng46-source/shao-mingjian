/* Optional local E2E flow. It is intentionally not a production dependency.
 * Run after installing Playwright in the local test environment:
 *   npm install --no-save playwright
 *   node scripts/phase7_browser_flow.mjs
 */

import fs from 'node:fs/promises';
import path from 'node:path';

const baseUrl = process.env.SST_DEMO_URL || 'http://127.0.0.1:8000';
const outputDir = path.resolve('output/playwright');
let chromium;

try {
  ({ chromium } = await import('playwright'));
} catch (error) {
  console.error('未找到 Playwright。请在本地测试环境运行 npm install --no-save playwright 后重试。');
  console.error(String(error));
  process.exit(2);
}

await fs.mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const checks = [];

try {
  await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' });
  checks.push({ name: 'page_loaded', passed: (await page.title()).includes('SST') });

  await page.getByRole('button', { name: /真实物理计算/ }).click();
  await page.locator('#physicalStatusBtn').click();
  await page.locator('#physicalRunBtn').click();
  await page.waitForFunction(() => !document.querySelector('#physicalExportJson')?.disabled, null, { timeout: 180000 });
  checks.push({ name: 'physical_candidate_result', passed: await page.locator('#physicalResultContent').isVisible() });
  await page.screenshot({ path: path.join(outputDir, 'phase7-physical.png'), fullPage: true });

  await page.getByRole('button', { name: /真实结构优化/ }).click();
  await page.locator('#optimizationRunBtn').click();
  await page.waitForFunction(() => !document.querySelector('#optimizationExportJson')?.disabled, null, { timeout: 300000 });
  checks.push({ name: 'optimization_result', passed: await page.locator('#optimizationSelectedContent').isVisible() });
  checks.push({ name: 'candidate_tabs', passed: await page.locator('.optimization-tab').count() === 3 });
  await page.locator('#optimizationCandidateSort').selectOption('volume');
  await page.locator('#optimizationCandidateFilter').fill('PS');
  const filteredRows = await page.locator('#optimizationCandidateTable tbody tr').allTextContents();
  checks.push({ name: 'candidate_filter_and_sort', passed: filteredRows.length > 0 && filteredRows.every((text) => text.includes('PS')) });
  await page.screenshot({ path: path.join(outputDir, 'phase7-optimization.png'), fullPage: true });

  await page.locator('#optimizationExportJson').click();
  checks.push({ name: 'optimization_export_button', passed: true });
  const report = { baseUrl, checks, passed: checks.every((item) => item.passed), note: '真实 Provider、显式波形和运行预算取决于启动环境。' };
  await fs.writeFile(path.join(outputDir, 'phase7-browser-flow.json'), JSON.stringify(report, null, 2), 'utf8');
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.passed ? 0 : 1;
} catch (error) {
  const report = { baseUrl, checks, passed: false, error: String(error) };
  await fs.writeFile(path.join(outputDir, 'phase7-browser-flow.json'), JSON.stringify(report, null, 2), 'utf8');
  console.error(JSON.stringify(report, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
