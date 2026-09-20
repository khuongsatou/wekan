'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const middleware = fs.readFileSync('server/apiMiddleware.js', 'utf8');
const requestUser = fs.readFileSync('server/lib/requestUser.js', 'utf8');

test('REST middleware resolves dedicated API tokens before legacy login tokens', () => {
  assert.match(middleware, /verifyApiToken/);
  assert.match(middleware, /req\.apiTokenId/);
  assert.match(middleware, /apiToken/);
  assert.match(middleware, /Authorization/);
});

test('request user resolution supports dedicated API tokens without MCP keys', () => {
  assert.match(requestUser, /verifyApiToken/);
  assert.match(requestUser, /apiToken/);
  assert.doesNotMatch(requestUser, /wk_mcp_/);
});

test('legacy token and MCP authentication paths remain present', () => {
  assert.match(middleware, /Accounts\._hashLoginToken/);
  assert.match(middleware, /x-api-key/);
  assert.match(middleware, /req\.mcpApiKeyId/);
});

test('dedicated REST tokens are not accepted through query strings', () => {
  assert.match(middleware, /access_token/);
  assert.match(middleware, /API_TOKEN_PREFIX/);
  assert.match(requestUser, /authToken/);
  assert.match(requestUser, /API_TOKEN_PREFIX/);
  assert.match(middleware, /redact|redacted|sanitize/i);
});
