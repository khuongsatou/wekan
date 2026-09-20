import { Meteor } from 'meteor/meteor';
import { ReactiveVar } from 'meteor/reactive-var';
import { Template } from 'meteor/templating';
import { TAPi18n } from '/imports/i18n';

const formatDate = value => value ? new Date(value).toLocaleString() : TAPi18n.__('api-token-never');
function decorateToken(token) {
  const now = new Date();
  const expiresAt = token.expiresAt ? new Date(token.expiresAt) : null;
  const state = token.revokedAt ? 'revoked' : expiresAt && expiresAt <= now ? 'expired' : 'active';
  return { ...token, createdLabel: formatDate(token.createdAt), expiresLabel: formatDate(token.expiresAt), lastUsedLabel: formatDate(token.lastUsedAt), stateLabel: TAPi18n.__('api-token-' + state), ownerLabel: token.username || token.fullname || token.userId || '' };
}
async function loadTokens(template) {
  try {
    const values = template.isAdminMode ? await Meteor.callAsync('apiTokens.adminList') : await Meteor.callAsync('apiTokens.listMine');
    template.tokens.set((values || []).map(decorateToken));
  } catch (error) {
    template.statusMessage.set(TAPi18n.__('api-token-load-failed'));
  }
}
Template.apiTokenSettings.onCreated(function () {
  this.tokens = new ReactiveVar([]);
  this.createdSecret = new ReactiveVar('');
  this.statusMessage = new ReactiveVar('');
  this.isAdminMode = !!(Template.currentData() && Template.currentData().isAdmin);
  this.autorun(() => { if (Meteor.userId()) loadTokens(this); });
});
Template.apiTokenSettings.helpers({
  tokens() { return Template.instance().tokens.get(); },
  createdSecret() { return Template.instance().createdSecret.get(); },
  statusMessage() { return Template.instance().statusMessage.get(); },
  isAdminMode() { return Template.instance().isAdminMode; },
  currentUserId() { return Meteor.userId() || ''; },
});
Template.apiTokenSettings.events({
  async 'submit .js-create-api-token'(event, template) {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const result = await Meteor.callAsync('apiTokens.createMine', form.querySelector('.js-api-token-name').value, Number(form.querySelector('.js-api-token-expiry').value));
      template.createdSecret.set(result.apiToken);
      template.statusMessage.set(TAPi18n.__('api-token-created-success'));
      form.reset();
      await loadTokens(template);
    } catch (error) {
      template.statusMessage.set(TAPi18n.__(error && error.error || 'api-token-create-failed'));
    }
  },
  async 'click .js-revoke-api-token'(event, template) {
    if (!window.confirm(TAPi18n.__('api-token-revoke-confirm'))) return;
    try {
      await Meteor.callAsync(
        template.isAdminMode ? 'apiTokens.adminRevoke' : 'apiTokens.revokeMine',
        event.currentTarget.dataset.id,
      );
      template.statusMessage.set(TAPi18n.__('api-token-revoked-success'));
      await loadTokens(template);
    } catch (error) {
      template.statusMessage.set(TAPi18n.__(error && error.error || 'api-token-revoke-failed'));
    }
  },
  async 'click .js-copy-api-token'(event, template) {
    try { await navigator.clipboard.writeText(template.createdSecret.get()); template.statusMessage.set(TAPi18n.__('api-token-copied')); } catch (_) { template.statusMessage.set(TAPi18n.__('api-token-copy-failed')); }
  },
  'click .js-dismiss-api-token'(event, template) { template.createdSecret.set(''); },
});
