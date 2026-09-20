'use strict';

// Static guard for the public /plugin Codex plugin installation guide.
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = rel => fs.readFileSync(path.join(root, rel), 'utf8');

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

test('registers a public /plugin route with the plugin guide template', () => {
  const router = read('config/router.js');
  assert.ok(/FlowRouter\.route\('\/plugin'/.test(router), 'route exists');
  assert.ok(/name: 'plugin'/.test(router), 'route has a stable name');
  assert.ok(/content: 'pluginGuide'/.test(router), 'route renders the guide');
  assert.ok(!/name: 'plugin'[\s\S]{0,240}ensureSignedIn/.test(router), 'guide is public');
});

test('guide includes the target GitHub repository and installation steps', () => {
  const jade = read('client/components/main/pluginGuide.jade');
  assert.ok(jade.includes('https://github.com/khuongsatou/mtips5s_wekan_plugin'), 'GitHub link');
  assert.ok(jade.includes('Cách cài plugin cho Codex'), 'installation heading');
  assert.ok((jade.match(/^\s*li\s/gm) || []).length >= 5, 'five installation steps');
  assert.ok(jade.includes('Plugins'), 'Codex Plugins destination');
});

test('guide is imported and has responsive visual styling', () => {
  const features = read('client/features/main.js');
  const css = read('client/components/main/pluginGuide.css');
  assert.ok(features.includes("'/client/components/main/pluginGuide.jade'"), 'template import');
  assert.ok(features.includes("'/client/components/main/pluginGuide.css'"), 'style import');
  assert.ok(css.includes('@media'), 'responsive layout');
  assert.ok(css.includes('backdrop-filter'), 'glass surface');
  assert.ok(css.includes('linear-gradient'), 'gradient accent');
});

console.log('pluginGuide:');
console.log(`\npluginGuide: ${passed} tests passed`);
