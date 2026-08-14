'use strict';

function escapeRegex(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function parseBoundedInteger(searchParams, name, defaultValue, min, max) {
  const raw = searchParams.get(name);
  if (raw === null || raw === '') return { ok: true, value: defaultValue };
  if (!/^\d+$/.test(raw)) {
    return { ok: false, error: `${name} must be an integer between ${min} and ${max}` };
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    return { ok: false, error: `${name} must be an integer between ${min} and ${max}` };
  }
  return { ok: true, value };
}

function parseDate(searchParams, name) {
  const raw = searchParams.get(name);
  if (!raw) return { ok: true, value: null };
  const value = new Date(raw);
  if (Number.isNaN(value.getTime())) {
    return { ok: false, error: `${name} must be an ISO date` };
  }
  return { ok: true, value };
}

function parseCardSearchParams(searchParams) {
  const limit = parseBoundedInteger(searchParams, 'limit', 50, 1, 100);
  if (!limit.ok) return limit;
  const offset = parseBoundedInteger(searchParams, 'offset', 0, 0, 10000);
  if (!offset.ok) return offset;

  const archivedRaw = searchParams.get('archived');
  const archivedValues = new Map([
    ['true', true],
    ['1', true],
    ['yes', true],
    ['false', false],
    ['0', false],
    ['no', false],
  ]);
  const archivedKey = String(archivedRaw || 'false').toLowerCase();
  if (!archivedValues.has(archivedKey)) {
    return { ok: false, error: 'archived must be true or false' };
  }

  const dueFrom = parseDate(searchParams, 'dueFrom');
  if (!dueFrom.ok) return dueFrom;
  const dueTo = parseDate(searchParams, 'dueTo');
  if (!dueTo.ok) return dueTo;
  if (dueFrom.value && dueTo.value && dueFrom.value > dueTo.value) {
    return { ok: false, error: 'dueFrom must not be later than dueTo' };
  }

  const query = String(searchParams.get('query') || '').trim();
  if (query.length > 500) {
    return { ok: false, error: 'query must not exceed 500 characters' };
  }

  return {
    ok: true,
    value: {
      query,
      boardId: searchParams.get('boardId'),
      listId: searchParams.get('listId'),
      swimlaneId: searchParams.get('swimlaneId'),
      memberId: searchParams.get('memberId'),
      assigneeId: searchParams.get('assigneeId'),
      labelId: searchParams.get('labelId'),
      archived: archivedValues.get(archivedKey),
      dueFrom: dueFrom.value,
      dueTo: dueTo.value,
      limit: limit.value,
      offset: offset.value,
    },
  };
}

function buildCardSearchSelector({
  boardIds = [],
  assignedOnlyBoardIds = [],
  userId,
  query,
  listId,
  swimlaneId,
  memberId,
  assigneeId,
  labelId,
  archived = false,
  dueFrom,
  dueTo,
} = {}) {
  const normalIds = boardIds.filter(id => !assignedOnlyBoardIds.includes(id));
  const assignedIds = boardIds.filter(id => assignedOnlyBoardIds.includes(id));
  const and = [];

  if (assignedIds.length > 0) {
    const boardBranches = [];
    if (normalIds.length > 0) boardBranches.push({ boardId: { $in: normalIds } });
    boardBranches.push({
      $and: [
        { boardId: { $in: assignedIds } },
        { $or: [{ members: userId }, { assignees: userId }] },
      ],
    });
    and.push({ $or: boardBranches });
  } else {
    and.push({ boardId: { $in: normalIds } });
  }

  and.push({ archived: !!archived });
  if (listId) and.push({ listId });
  if (swimlaneId) and.push({ swimlaneId });
  if (memberId) and.push({ members: memberId });
  if (assigneeId) and.push({ assignees: assigneeId });
  if (labelId) and.push({ labelIds: labelId });
  if (query && String(query).trim()) {
    const regex = new RegExp(escapeRegex(String(query).trim()), 'i');
    and.push({ $or: [{ title: regex }, { description: regex }] });
  }
  if (dueFrom || dueTo) {
    const dueAt = {};
    if (dueFrom) dueAt.$gte = dueFrom;
    if (dueTo) dueAt.$lte = dueTo;
    and.push({ dueAt });
  }

  return { $and: and };
}

module.exports = {
  buildCardSearchSelector,
  escapeRegex,
  parseCardSearchParams,
};
