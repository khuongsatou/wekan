'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const urls = fs.readFileSync('models/lib/adminUrls.js', 'utf8');
const people = fs.readFileSync('client/components/settings/peopleBody.js', 'utf8');
const routing = fs.readFileSync('config/router.js', 'utf8');
const memberMenu = fs.readFileSync('client/components/users/userHeader.jade', 'utf8');
const pluginReadme = fs.readFileSync('tools/ai-systems-mcp/README.md', 'utf8');

test('defines the admin API token pane and personal token route', () => {
  assert.match(urls, /'api-tokens':\s*'api-tokens-setting'/);
  assert.match(urls, /'api-tokens-setting'/);
  assert.match(people, /api-tokens-setting/);
  assert.match(routing, /api-tokens/);
  assert.match(memberMenu, /api-tokens/);
});

test('UI uses dedicated token methods and one-time secret behavior', () => {
  const jade = fs.readFileSync('client/components/settings/apiTokens.jade', 'utf8');
  const js = fs.readFileSync('client/components/settings/apiTokens.js', 'utf8');
  assert.match(js, /apiTokens\.listMine/);
  assert.match(js, /apiTokens\.createMine/);
  assert.match(js, /apiTokens\.revokeMine/);
  assert.match(js, /apiTokens\.adminList/);
  assert.match(js, /apiTokens\.adminRevoke/);
  assert.match(jade, /WEKAN_USER_ID/);
  assert.match(jade, /WEKAN_API_TOKEN/);
  assert.match(jade, /wk_api_/);
  assert.match(jade, /wk_mcp_/);
});

test('plugin documentation uses the runtime URL variable and separates token types', () => {
  assert.match(pluginReadme, /WEKAN_BASE_URL=/);
  assert.doesNotMatch(pluginReadme, /WEKAN_URL=/);
  assert.match(pluginReadme, /WEKAN_USER_ID=/);
  assert.match(pluginReadme, /WEKAN_API_TOKEN=wk_api_/);
});
