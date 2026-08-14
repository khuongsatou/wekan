'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'server', 'models', 'cards.js'),
  'utf8',
);
const start = source.indexOf("'/api/boards/:boardId/lists/:listId/cards/:cardId/copy'");
const end = source.indexOf('// Issue #4815:', start);
assert.ok(start >= 0 && end > start, 'card copy route exists');
const route = source.slice(start, end);

assert.match(route, /checkBoardWriteAccess\(req\.userId, toBoardId\)/,
  'destination board requires write access');
assert.match(route, /getList\(\{ _id: toListId, boardId: toBoardId, archived: false \}\)/,
  'destination list must belong to the destination board');
assert.match(route, /getSwimlane\(\{[\s\S]*_id: toSwimlaneId,[\s\S]*boardId: toBoardId/,
  'destination swimlane must belong to the destination board');
assert.match(route, /boardId: toBoardId,[\s\S]*listId: toListId,[\s\S]*swimlaneId: toSwimlaneId/,
  'positioning cannot mix cards from another board or swimlane');

console.log('restCardCopyRoute: 4 checks passed');
