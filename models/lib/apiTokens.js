'use strict';

const crypto = require('node:crypto');

const API_TOKEN_PREFIX = 'wk_api_';
const API_TOKEN_EXPIRY_DAYS = [30, 90, 365];
const MAX_ACTIVE_API_TOKENS_PER_USER = 10;

function isApiToken(value) {
  return typeof value === 'string' &&
    value.startsWith(API_TOKEN_PREFIX) &&
    value.length >= API_TOKEN_PREFIX.length + 24;
}

function hashApiToken(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function normalizeApiTokenName(value) {
  if (typeof value !== 'string') return '';
  return value.trim().replace(/\s+/g, ' ').slice(0, 80);
}

function apiTokenExpiryDate(days, now = new Date()) {
  if (!Number.isInteger(days) || !API_TOKEN_EXPIRY_DAYS.includes(days)) return null;
  return new Date(now.getTime() + days * 24 * 60 * 60 * 1000);
}

function publicApiToken(doc) {
  return {
    _id: doc._id,
    userId: doc.userId,
    name: doc.name,
    prefix: doc.prefix,
    createdAt: doc.createdAt,
    lastUsedAt: doc.lastUsedAt || null,
    expiresAt: doc.expiresAt,
    revokedAt: doc.revokedAt || null,
  };
}

module.exports = {
  API_TOKEN_PREFIX,
  API_TOKEN_EXPIRY_DAYS,
  MAX_ACTIVE_API_TOKENS_PER_USER,
  isApiToken,
  hashApiToken,
  normalizeApiTokenName,
  apiTokenExpiryDate,
  publicApiToken,
};
