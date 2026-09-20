'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const read = rel => fs.readFileSync(path.join(ROOT, rel), 'utf8');

const base = read('client/components/main/appleGlassPastel.css');
const pages = read('client/components/boards/appleGlassPastelPages.css');

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log('  ok -', name);
}

console.log('uiUxAccessibilityTokens:');

test('modern UI/UX design tokens are declared in shared theme layer', () => {
  const expectedTokens = [
    '--agp-shadow-subtle',
    '--agp-shadow-lifted',
    '--agp-focus-ring',
    '--agp-success-bg',
    '--agp-success-text',
    '--agp-warning-bg',
    '--agp-warning-text',
    '--agp-danger-bg',
    '--agp-danger-text',
  ];
  for (const token of expectedTokens) {
    assert.ok(base.includes(token), `Token ${token} must be declared in appleGlassPastel.css`);
  }
});

test('accessibility focus-visible ring is enhanced', () => {
  assert.ok(base.includes('body.board-color-appleglasspastel :focus-visible'),
    'focus-visible rule must exist');
  assert.ok(base.includes('box-shadow: var(--agp-focus-ring)'),
    'focus-visible rule must apply --agp-focus-ring');
});

test('minicard visual hierarchy and badge status styles are present', () => {
  assert.ok(pages.includes('.minicard-title') && pages.includes('font-weight: 600'),
    'minicard title has strong readable typography');
  assert.ok(pages.includes('.minicard .badges .badge'),
    'minicard badges have modern pill styling');
  assert.ok(pages.includes('.card-date.due-date.due-overdue')
    && pages.includes('var(--agp-danger-bg)'),
    'overdue due-dates show urgent danger styling');
  assert.ok(pages.includes('.badge.is-finished')
    && pages.includes('var(--agp-success-bg)'),
    'completed checklist badges show success styling');
});

test('stacked avatar group and drag-and-drop feedback are defined', () => {
  assert.ok(pages.includes('.minicard-members .member')
    && pages.includes('margin-inline-start: -6px'),
    'avatars stack horizontally with negative margin');
  assert.ok(pages.includes('.minicard-wrapper.ui-sortable-helper')
    && pages.includes('transform: rotate(2deg) scale(1.02)'),
    'dragging card helper has subtle tilt and lifted shadow');
  assert.ok(pages.includes('.minicard-wrapper.placeholder')
    && pages.includes('dashed'),
    'drop placeholder has dashed outline and soft tint');
});

test('sticky list headers and card details modal polish are defined', () => {
  assert.ok(pages.includes('.board-color-appleglasspastel.board-wrapper .list-header')
    && pages.includes('position: sticky'),
    'list header is sticky');
  assert.ok(pages.includes('.list-header-card-count'),
    'list header card count badge exists');
  assert.ok(pages.includes('.checklist-progress-bar'),
    'card details modal includes checklist progress bar styling');
  assert.ok(pages.includes('.card-details-item-buttons'),
    'card details modal action buttons are polished');
});

console.log(`\n${passed} tests passed`);
