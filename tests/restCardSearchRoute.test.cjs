'use strict';

// Route-wiring checks for GET /api/search/cards. Selector and input behavior are
// covered in restCardSearch.test.cjs; this pins the security scope and database
// pagination that are assembled in the Meteor handler.

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'server', 'models', 'cards.js'),
  'utf8',
);
const start = source.indexOf("WebApp.handlers.get('/api/search/cards'");
assert.ok(start >= 0, 'search endpoint is registered');
const route = source.slice(start);

assert.match(route, /if \(!req\.userId\)[\s\S]*code: 401/, 'anonymous search is denied');
assert.match(route, /parseCardSearchParams\(/, 'query validation runs before searching');
assert.match(route, /Boards\.userBoards\(/, 'board visibility is derived server-side');
assert.match(
  route,
  /\{ includePublic: !!requestedBoardId \}/,
  'global search excludes unrelated public boards while explicit public boards remain visible',
);
assert.match(
  route,
  /requestedBoardId && boards\.length === 0[\s\S]*code: 403/,
  'an explicitly requested inaccessible private board is denied',
);
assert.match(
  route,
  /isNormalAssignedOnly[\s\S]*isCommentAssignedOnly[\s\S]*isReadAssignedOnly/,
  'all assigned-only roles are retained',
);
assert.match(route, /skip: params\.offset/, 'pagination offset reaches Mongo');
assert.match(route, /limit: params\.limit/, 'pagination limit reaches Mongo');
assert.match(route, /Cards\.find\(selector\)\.countAsync\(\)/, 'total uses the same selector');

console.log('restCardSearchRoute: 9 checks passed');
