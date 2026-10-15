import { expect, test } from '@playwright/test';

const SYMBOLS = ['NOK', 'DRAM', 'QNT', 'SKHY'];

async function openDashboard(page, { allowTradingView = false } = {}) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && !/tradingview|Failed to load resource/i.test(message.text())) errors.push(message.text());
  });
  if (!allowTradingView) await page.route('**/s3.tradingview.com/**', (route) => route.abort());
  await page.goto('/');
  await expect(page.locator('#portfolio-body .hero__value')).toContainText(/\d/, { timeout: 15_000 });
  return errors;
}

test('loads the portfolio, holdings and every section without errors', async ({ page }) => {
  const errors = await openDashboard(page);

  await expect(page).toHaveTitle('美股持股觀測站');
  await expect(page.locator('.hero__value')).toContainText('US$');
  const rows = page.locator('#holdings-body tr.position .ticker__symbol');
  await expect(rows).toHaveText(SYMBOLS);
  await expect(page.locator('.alloc__legend li')).toHaveCount(4);
  await expect(page.locator('#market-pulse .tile')).toHaveCount(8);
  await expect(page.locator('#news-body .news-item').first()).toBeVisible();
  await expect(page.locator('#earnings-body .event').first()).toBeVisible();
  await expect(page.locator('#macro-body .event').first()).toBeVisible();
  await expect(page.locator('#session')).toContainText(/美股|休市/);
  expect(errors).toEqual([]);
});

test('news filters narrow the list and are kept in the URL', async ({ page }) => {
  await openDashboard(page);

  await page.getByRole('button', { name: /^SKHY \d+$/ }).click();

  await expect(page).toHaveURL(/news=sym%3ASKHY|news=sym:SKHY/);
  const badges = page.locator('#news-body .news-item');
  const count = await badges.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < Math.min(count, 10); i += 1) {
    await expect(badges.nth(i).locator('.badge.mono', { hasText: 'SKHY' })).toHaveCount(1);
  }

  await page.reload();
  await expect(page.getByRole('button', { name: /^SKHY \d+$/ })).toHaveAttribute('aria-pressed', 'true');
});

test('cost basis entered in settings stays in this browser and drives P/L', async ({ page }) => {
  await openDashboard(page);

  await page.getByRole('button', { name: '設定' }).click();
  await page.getByRole('textbox', { name: 'NOK' }).fill('8');
  await page.getByRole('button', { name: '儲存' }).click();

  await expect(page.locator('.stat', { hasText: '未實現損益' })).toContainText('US$');
  const stored = await page.evaluate(() => JSON.parse(window.localStorage.getItem('fw.settings.v1')));
  expect(stored.costs).toEqual({ NOK: 8 });

  await page.getByRole('button', { name: '設定' }).click();
  await page.getByRole('textbox', { name: 'DRAM' }).fill('-3');
  await page.getByRole('button', { name: '儲存' }).click();
  await expect(page.getByRole('alert').filter({ hasText: '成本價格式不正確' })).toBeVisible();
});

test('a holding row expands to show drivers and earnings info', async ({ page }) => {
  await openDashboard(page);

  await page.getByRole('button', { name: 'NOK 詳細資料' }).click();

  const details = page.locator('#details-NOK');
  await expect(details).toContainText('觀察重點');
  await expect(details).toContainText('財報（法說會）');
  await expect(page.getByRole('button', { name: 'NOK 詳細資料' })).toHaveAttribute('aria-expanded', 'true');
});

test('colour convention switch flips rise / fall colours', async ({ page }) => {
  await openDashboard(page);
  const rise = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--rise').trim());
  const red = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--red').trim());

  expect(await rise()).toBe(red);
  await page.getByRole('button', { name: '設定' }).click();
  await page.locator('#set-updown').selectOption('us');
  await page.getByRole('button', { name: '儲存' }).click();
  expect(await rise()).not.toBe(red);
});

test('layout never scrolls horizontally', async ({ page }) => {
  await openDashboard(page);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('visual snapshot for review', async ({ page }, testInfo) => {
  await openDashboard(page, { allowTradingView: true });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: testInfo.outputPath(`dashboard-${testInfo.project.name}.png`), fullPage: true });
});
