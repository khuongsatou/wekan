const { Meteor } = require('meteor/meteor');
const { Mongo } = require('meteor/mongo');
const { Random } = require('meteor/random');
const {
  API_TOKEN_PREFIX,
  API_TOKEN_EXPIRY_DAYS,
  MAX_ACTIVE_API_TOKENS_PER_USER,
  isApiToken,
  hashApiToken,
  normalizeApiTokenName,
  apiTokenExpiryDate,
  publicApiToken,
} = require('/models/lib/apiTokens');

const ApiTokens = new Mongo.Collection('apiTokens');

async function createApiToken(userId, name, expiresInDays, now = new Date()) {
  if (!userId) throw new Meteor.Error('not-authorized');
  const normalizedName = normalizeApiTokenName(name);
  if (!normalizedName) throw new Meteor.Error('api-token-name-required');
  const expiresAt = apiTokenExpiryDate(expiresInDays, now);
  if (!expiresAt) throw new Meteor.Error('api-token-expiry-invalid');

  const activeCount = await ApiTokens.find({
    userId,
    revokedAt: null,
    expiresAt: { $gt: now },
  }).countAsync();
  if (activeCount >= MAX_ACTIVE_API_TOKENS_PER_USER) {
    throw new Meteor.Error('api-token-limit-reached');
  }

  const apiToken = `${API_TOKEN_PREFIX}${Random.secret(36)}`;
  const id = await ApiTokens.insertAsync({
    userId,
    name: normalizedName,
    tokenHash: hashApiToken(apiToken),
    prefix: apiToken.slice(0, API_TOKEN_PREFIX.length + 8),
    createdAt: now,
    lastUsedAt: null,
    expiresAt,
    revokedAt: null,
  });

  return {
    apiToken,
    token: publicApiToken(await ApiTokens.findOneAsync(id)),
  };
}

async function verifyApiToken(value, now = new Date()) {
  if (!isApiToken(value)) return null;
  const token = await ApiTokens.findOneAsync({
    tokenHash: hashApiToken(value),
    revokedAt: null,
    expiresAt: { $gt: now },
  });
  if (!token) return null;

  const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000);
  await ApiTokens.updateAsync(
    {
      _id: token._id,
      $or: [
        { lastUsedAt: null },
        { lastUsedAt: { $lt: fiveMinutesAgo } },
      ],
    },
    { $set: { lastUsedAt: now } },
  );

  return { tokenId: token._id, userId: token.userId };
}

async function listApiTokensForUser(userId) {
  if (!userId) throw new Meteor.Error('not-authorized');
  return (await ApiTokens.find(
    { userId },
    { sort: { createdAt: -1 }, limit: 50 },
  ).fetchAsync()).map(publicApiToken);
}

async function listApiTokensForAdmin() {
  const tokens = await ApiTokens.find({}, { sort: { createdAt: -1 }, limit: 500 }).fetchAsync();
  const userIds = [...new Set(tokens.map(token => token.userId))];
  const users = await Meteor.users.find(
    { _id: { $in: userIds } },
    { fields: { username: 1, 'profile.fullname': 1 } },
  ).fetchAsync();
  const byId = new Map(users.map(user => [user._id, user]));
  return tokens.map(token => ({
    ...publicApiToken(token),
    username: byId.get(token.userId)?.username || '',
    fullname: byId.get(token.userId)?.profile?.fullname || '',
  }));
}

async function revokeApiToken(requesterId, tokenId, admin = false) {
  if (!requesterId) throw new Meteor.Error('not-authorized');
  const selector = admin
    ? { _id: tokenId, revokedAt: null }
    : { _id: tokenId, userId: requesterId, revokedAt: null };
  const result = await ApiTokens.updateAsync(
    selector,
    { $set: { revokedAt: new Date() } },
  );
  if (!result) throw new Meteor.Error('api-token-not-found');
  return { revoked: true, tokenId };
}

module.exports = {
  ApiTokens,
  createApiToken,
  verifyApiToken,
  listApiTokensForUser,
  listApiTokensForAdmin,
  revokeApiToken,
};
