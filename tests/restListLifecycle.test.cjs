'use strict';

// REST list lifecycle wiring. In particular, a same-board copy must create a
// distinct list rather than finding the source by its title and copying cards
// back into it; a cross-board move must archive the emptied source list.

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'server', 'models', 'lists.js'),
  'utf8',
);
const copyStart = source.indexOf("'/api/boards/:boardId/lists/:listId/copy'");
const moveStart = source.indexOf("'/api/boards/:boardId/lists/:listId/move'");
assert.ok(copyStart >= 0 && moveStart > copyStart, 'list copy/move routes exist');
const copy = source.slice(copyStart, moveStart);
const move = source.slice(moveStart);

assert.match(copy, /destinationSwimlaneId\(/, 'copy resolves a real destination swimlane');
assert.match(copy, /const newId = await Lists\.insertAsync\(/, 'copy always inserts a new list');
assert.doesNotMatch(copy, /list\.copy\(/, 'copy never reuses the source list by title');
assert.match(copy, /await card\.copy\(toBoardId, toSwimlaneId, newId\)/,
  'cards are copied into the new list and swimlane');
assert.match(move, /await card\.move\(toBoardId, toSwimlaneId, destinationList\._id\)/,
  'cross-board card moves use the destination swimlane and list');
assert.match(move, /await list\.archive\(\)/, 'cross-board move archives the emptied source list');
assert.match(move, /data: \{ _id: destinationList\._id \}/,
  'move returns the destination list id');

console.log('restListLifecycle: 7 checks passed');
