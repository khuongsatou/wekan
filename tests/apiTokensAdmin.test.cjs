'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const server = fs.readFileSync('server/apiTokens.js', 'utf8');
const library = fs.readFileSync('server/lib/apiTokens.js', 'utf8');
const template = fs.readFileSync('client/components/settings/apiTokens.jade', 'utf8');

test('admin token methods require the server-side site-admin check', () => {
  assert.match(server, /apiTokens\.adminList/);
  assert.match(server, /apiTokens\.adminRevoke/);
  assert.match(server, /currentUser\(this\.userId\)/);
  assert.match(server, /!user\?\.isAdmin/);
  assert.doesNotMatch(server, /apiTokens\.adminCreate/);
});

test('admin metadata never includes secret-bearing fields', () => {
  assert.match(library, /fields: \{ username: 1, 'profile\.fullname': 1 \}/);
  assert.match(library, /\.\.\.publicApiToken\(token\)/);
  assert.match(template, /unless isAdminMode/);
});
