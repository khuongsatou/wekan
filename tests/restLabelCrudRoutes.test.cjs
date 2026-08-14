'use strict';

// Static wiring checks complement the pure restLabel tests. The route handlers
// depend on Meteor collections, but these invariants must remain visible in the
// source: explicit auth failures, shared validation, and non-direct deletion so
// the existing Boards.after.update card-cleanup hook runs.

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'server', 'models', 'boards.js'),
  'utf8',
);

function routeBlock(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `route block not found: ${start}`);
  return source.slice(from, to);
}

const update = routeBlock(
  "WebApp.handlers.put('/api/boards/:boardId/labels/:labelId'",
  "WebApp.handlers.delete('/api/boards/:boardId/labels/:labelId'",
);
const remove = routeBlock(
  "WebApp.handlers.delete('/api/boards/:boardId/labels/:labelId'",
  '// Issue #3062:',
);

assert.match(update, /if \(!req\.userId\)/, 'label update denies unauthenticated calls');
assert.match(update, /code: 403/, 'label update denies non-admin board members');
assert.match(update, /buildBoardLabelUpdate\(/, 'label update uses tested validation');
assert.match(remove, /if \(!req\.userId\)/, 'label delete denies unauthenticated calls');
assert.match(remove, /code: 403/, 'label delete denies non-admin board members');
assert.match(remove, /code: 404/, 'label delete reports an unknown label');
assert.match(
  remove,
  /Boards\.updateAsync[\s\S]*\$pull: \{ labels: \{ _id: labelId \} \}/,
  'label deletion uses the observed collection update path',
);
assert.match(
  source,
  /Boards\.after\.update[\s\S]*removedLabelId[\s\S]*Cards\.updateAsync[\s\S]*labelIds: removedLabelId/,
  'the board hook removes a deleted label from cards',
);

console.log('restLabelCrudRoutes: 8 checks passed');
