'use strict';

const assert = require('assert');
const {
  buildCardSearchSelector,
  escapeRegex,
  parseCardSearchParams,
} = require('../models/lib/restCardSearch');

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

test('escapes free text instead of accepting executable regex input', () => {
  assert.strictEqual(escapeRegex('a.*(b)'), 'a\\.\\*\\(b\\)');
});

test('scopes normal boards and defaults to active cards', () => {
  const selector = buildCardSearchSelector({ boardIds: ['b1', 'b2'], userId: 'u1' });
  assert.deepStrictEqual(selector.$and[0], { boardId: { $in: ['b1', 'b2'] } });
  assert.deepStrictEqual(selector.$and[1], { archived: false });
});

test('assigned-only boards require card membership or assignment', () => {
  const selector = buildCardSearchSelector({
    boardIds: ['normal', 'assigned'],
    assignedOnlyBoardIds: ['assigned'],
    userId: 'u1',
  });
  assert.deepStrictEqual(selector.$and[0].$or[1], {
    $and: [
      { boardId: { $in: ['assigned'] } },
      { $or: [{ members: 'u1' }, { assignees: 'u1' }] },
    ],
  });
});

test('adds text, identity, label, location, archive and due filters', () => {
  const from = new Date('2026-01-01T00:00:00.000Z');
  const to = new Date('2026-02-01T00:00:00.000Z');
  const selector = buildCardSearchSelector({
    boardIds: ['b1'],
    userId: 'u1',
    query: 'login.*',
    listId: 'l1',
    swimlaneId: 's1',
    memberId: 'm1',
    assigneeId: 'a1',
    labelId: 'x1',
    archived: true,
    dueFrom: from,
    dueTo: to,
  });
  assert.ok(selector.$and.some(item => item.archived === true));
  assert.ok(selector.$and.some(item => item.listId === 'l1'));
  assert.ok(selector.$and.some(item => item.swimlaneId === 's1'));
  assert.ok(selector.$and.some(item => item.members === 'm1'));
  assert.ok(selector.$and.some(item => item.assignees === 'a1'));
  assert.ok(selector.$and.some(item => item.labelIds === 'x1'));
  assert.ok(selector.$and.some(item => item.dueAt && item.dueAt.$gte === from));
  const text = selector.$and.find(item => item.$or && item.$or[0] && item.$or[0].title);
  assert.strictEqual(text.$or[0].title.test('LOGIN.*'), true);
  assert.strictEqual(text.$or[0].title.test('login-anything'), false);
});

test('an empty board scope matches no cards', () => {
  const selector = buildCardSearchSelector({ boardIds: [], userId: 'u1' });
  assert.deepStrictEqual(selector.$and[0], { boardId: { $in: [] } });
});

test('parses pagination, booleans and due dates without silently clamping', () => {
  const parsed = parseCardSearchParams(new URLSearchParams({
    archived: 'yes',
    limit: '25',
    offset: '50',
    dueFrom: '2026-01-01T00:00:00.000Z',
    dueTo: '2026-02-01T00:00:00.000Z',
  }));
  assert.strictEqual(parsed.ok, true);
  assert.strictEqual(parsed.value.archived, true);
  assert.strictEqual(parsed.value.limit, 25);
  assert.strictEqual(parsed.value.offset, 50);
  assert.ok(parsed.value.dueFrom instanceof Date);
});

test('uses bounded defaults when pagination is omitted', () => {
  const parsed = parseCardSearchParams(new URLSearchParams());
  assert.strictEqual(parsed.ok, true);
  assert.strictEqual(parsed.value.limit, 50);
  assert.strictEqual(parsed.value.offset, 0);
  assert.strictEqual(parsed.value.archived, false);
});

test('rejects invalid limits, offsets and archived flags', () => {
  for (const params of [
    { limit: '0' },
    { limit: '101' },
    { limit: '1.5' },
    { offset: '-1' },
    { offset: '10001' },
    { archived: 'sometimes' },
  ]) {
    assert.strictEqual(parseCardSearchParams(new URLSearchParams(params)).ok, false);
  }
});

test('rejects invalid or reversed due date ranges', () => {
  assert.strictEqual(
    parseCardSearchParams(new URLSearchParams({ dueFrom: 'not-a-date' })).ok,
    false,
  );
  assert.strictEqual(
    parseCardSearchParams(new URLSearchParams({
      dueFrom: '2026-02-01T00:00:00.000Z',
      dueTo: '2026-01-01T00:00:00.000Z',
    })).ok,
    false,
  );
});

test('trims text and rejects oversized regex input before Mongo sees it', () => {
  const parsed = parseCardSearchParams(new URLSearchParams({ query: '  login bug  ' }));
  assert.strictEqual(parsed.ok, true);
  assert.strictEqual(parsed.value.query, 'login bug');
  assert.strictEqual(
    parseCardSearchParams(new URLSearchParams({ query: 'x'.repeat(501) })).ok,
    false,
  );
});

console.log(`\n${passed} tests passed`);
