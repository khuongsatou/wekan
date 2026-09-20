'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const source = fs.readFileSync('server/lib/apiTokens.js', 'utf8');
const methods = fs.readFileSync('server/apiTokens.js', 'utf8');

test('stores only a token hash and one-time secret creation result', () => {
  assert.match(source, /tokenHash:\s*hashApiToken\(apiToken\)/);
  assert.match(source, /apiToken,\s*\n\s*token:/);
  assert.doesNotMatch(source, /token:\s*apiToken/);
  assert.match(methods, /tokenHash:\s*1/);
});

test('enforces lifecycle limits and expiry/revocation', () => {
  assert.match(source, /MAX_ACTIVE_API_TOKENS_PER_USER/);
  assert.match(source, /revokedAt:\s*null/);
  assert.match(source, /expiresAt:\s*\{\s*\$gt:\s*now\s*\}/);
  assert.match(source, /lastUsedAt/);
});

test('exposes owner-only and admin-only methods', () => {
  for (const name of [
    "'apiTokens.listMine'",
    "'apiTokens.createMine'",
    "'apiTokens.revokeMine'",
    "'apiTokens.adminList'",
    "'apiTokens.adminRevoke'",
  ]) assert.match(methods, new RegExp(name.replace(/[']/g, "\\'")));
  assert.match(methods, /if \(!user\?\.isAdmin\) throw new Meteor\.Error\('not-authorized'\)/);
  assert.match(methods, /userId:\s*1/);
  assert.match(source, /profile\.fullname/);
  assert.doesNotMatch(source, /fields:[\s\S]*tokenHash/);
});
