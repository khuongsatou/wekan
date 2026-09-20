'use strict';

const { test, expect } = require('../fixtures');
const db = require('../helpers/db');
const { loginWithToken } = require('../helpers/auth');

test.describe('REST API tokens', () => {
  test('creates a one-time token, authenticates REST, and revokes it', async ({ page, request, user }) => {
    let tokenId = null;
    try {
      await loginWithToken(page, user.id, user.token);
      await page.goto('/api-tokens', { waitUntil: 'networkidle' });
      await expect(page.locator('.api-token-page')).toBeVisible();
      await expect(page.getByRole('region', { name: /REST API Tokens|Token API REST/ })).toBeVisible();
      await expect(page.locator('.api-token-panel')).toHaveCount(3);

      await page.locator('.js-api-token-name').fill('Playwright REST token');
      await page.locator('.js-api-token-expiry').selectOption('30');
      await page.locator('.js-create-api-token').dispatchEvent('submit');

      const secret = page.locator('.js-api-token-secret');
      await expect(secret).toBeVisible();
      const rawToken = await secret.inputValue();
      expect(rawToken).toMatch(/^wk_api_/);

      const row = page.locator('.api-token-row').filter({ hasText: 'Playwright REST token' });
      await expect(row).toBeVisible();
      tokenId = await row.locator('.js-revoke-api-token').getAttribute('data-id');

      const authenticated = await request.get('/api/user', {
        headers: { Authorization: `Bearer ${rawToken}` },
      });
      expect(authenticated.status()).toBe(200);
      expect((await authenticated.json())._id).toBe(user.id);

      await page.locator('.js-dismiss-api-token').click();
      await page.reload({ waitUntil: 'networkidle' });
      await expect(page.locator('.js-api-token-secret')).toHaveCount(0);
      await expect(page.locator('.api-token-row').filter({ hasText: 'wk_api_' })).toBeVisible();

      page.once('dialog', dialog => dialog.accept());
      await page.locator('.js-revoke-api-token').first().click();
      await expect(page.locator('.api-token-row').first()).toContainText(/Revoked|Đã thu hồi/);

      const rejected = await request.get('/api/user/cards', {
        headers: { Authorization: `Bearer ${rawToken}` },
        failOnStatusCode: false,
      });
      expect(rejected.status()).toBe(401);
    } finally {
      if (tokenId) db.deleteOne('apiTokens', { _id: tokenId });
    }
  });

  test('keeps the token page usable without horizontal overflow', async ({ page, user }) => {
    await loginWithToken(page, user.id, user.token);

    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/api-tokens', { waitUntil: 'networkidle' });

      await expect(page.locator('.api-token-page')).toBeVisible();
      await expect(page.locator('.js-api-token-name')).toBeVisible();
      await expect(page.locator('.js-api-token-expiry')).toBeVisible();
      await expect(page.locator('.js-create-api-token button[type="submit"]')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  });

  test('renders the admin token pane without user-only controls', async ({ page, adminUser }) => {
    await loginWithToken(page, adminUser.id, adminUser.token);
    await page.goto('/admin/people/api-tokens', { waitUntil: 'networkidle' });

    await expect(page.locator('.api-token-page')).toBeVisible();
    await expect(page.locator('.api-token-panel')).toHaveCount(1);
    await expect(page.locator('.js-create-api-token')).toHaveCount(0);
    await expect(page.locator('.api-token-config')).toHaveCount(0);
    await expect(page.locator('.side-menu li.active')).toContainText(/REST API Tokens|Token API REST/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
