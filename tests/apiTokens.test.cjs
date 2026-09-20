'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  API_TOKEN_PREFIX,
  API_TOKEN_EXPIRY_DAYS,
  MAX_ACTIVE_API_TOKENS_PER_USER,
  hashApiToken,
  normalizeApiTokenName,
  apiTokenExpiryDate,
  publicApiToken,
  isApiToken,
} = require('../models/lib/apiTokens');

test('defines a distinct REST token contract', () => {
  assert.equal(API_TOKEN_PREFIX, 'wk_api_');
  assert.deepEqual(API_TOKEN_EXPIRY_DAYS, [30, 90, 365]);
  assert.equal(MAX_ACTIVE_API_TOKENS_PER_USER, 10);
  assert.equal(isApiToken('wk_api_abcdefghijklmnopqrstuvwxyz'), true);
  assert.equal(isApiToken('wk_mcp_abcdefghijklmnopqrstuvwxyz'), false);
});

test('hashes a token deterministically without returning the raw secret', () => {
  const raw = 'wk_api_abcdefghijklmnopqrstuvwxyz';
  const hash = hashApiToken(raw);

  assert.equal(hash, hashApiToken(raw));
  assert.notEqual(hash, raw);
  assert.match(hash, /^[a-f0-9]{64}$/);
});

test('normalizes and bounds token names', () => {
  assert.equal(normalizeApiTokenName('  Claude   plugin\n  '), 'Claude plugin');
  assert.equal(normalizeApiTokenName('x'.repeat(100)).length, 80);
  assert.equal(normalizeApiTokenName('   '), '');
  assert.equal(normalizeApiTokenName(null), '');
});

test('calculates only supported expiry periods from an injected clock', () => {
  const now = new Date('2026-09-09T00:00:00.000Z');
  assert.equal(
    apiTokenExpiryDate(30, now).toISOString(),
    '2026-10-09T00:00:00.000Z',
  );
  assert.equal(apiTokenExpiryDate(7, now), null);
  assert.equal(apiTokenExpiryDate('90', now), null);
});

test('public metadata excludes hashes and raw secrets', () => {
  const publicToken = publicApiToken({
    _id: 'token-id',
    userId: 'user-id',
    name: 'Plugin',
    prefix: 'wk_api_abcdef12',
    keyHash: 'secret-hash',
    token: 'wk_api_raw-secret',
    createdAt: new Date('2026-09-09T00:00:00.000Z'),
    lastUsedAt: null,
    expiresAt: new Date('2026-12-08T00:00:00.000Z'),
    revokedAt: null,
  });

  assert.deepEqual(publicToken, {
    _id: 'token-id',
    userId: 'user-id',
    name: 'Plugin',
    prefix: 'wk_api_abcdef12',
    createdAt: new Date('2026-09-09T00:00:00.000Z'),
    lastUsedAt: null,
    expiresAt: new Date('2026-12-08T00:00:00.000Z'),
    revokedAt: null,
  });
  assert.equal('keyHash' in publicToken, false);
  assert.equal('token' in publicToken, false);
});
