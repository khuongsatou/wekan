import { Meteor } from 'meteor/meteor';
import { check } from 'meteor/check';
import { ensureIndex } from '/server/lib/mongoStartup';
const {
  ApiTokens,
  createApiToken,
  listApiTokensForUser,
  listApiTokensForAdmin,
  revokeApiToken,
} = require('/server/lib/apiTokens');

Meteor.startup(async () => {
  await ensureIndex(ApiTokens, { userId: 1, createdAt: -1 });
  await ensureIndex(ApiTokens, { tokenHash: 1 }, { unique: true });
  await ensureIndex(ApiTokens, { expiresAt: 1 });
});

async function currentUser(userId) {
  return userId ? Meteor.users.findOneAsync(
    { _id: userId },
    { fields: { isAdmin: 1 } },
  ) : null;
}

Meteor.methods({
  async 'apiTokens.listMine'() {
    return listApiTokensForUser(this.userId);
  },

  async 'apiTokens.createMine'(name, expiresInDays = 90) {
    check(name, String);
    check(expiresInDays, Number);
    return createApiToken(this.userId, name, expiresInDays);
  },

  async 'apiTokens.revokeMine'(tokenId) {
    check(tokenId, String);
    return revokeApiToken(this.userId, tokenId, false);
  },

  async 'apiTokens.adminList'() {
    const user = await currentUser(this.userId);
    if (!user?.isAdmin) throw new Meteor.Error('not-authorized');
    return listApiTokensForAdmin();
  },

  async 'apiTokens.adminRevoke'(tokenId) {
    check(tokenId, String);
    const user = await currentUser(this.userId);
    if (!user?.isAdmin) throw new Meteor.Error('not-authorized');
    return revokeApiToken(this.userId, tokenId, true);
  },
});
