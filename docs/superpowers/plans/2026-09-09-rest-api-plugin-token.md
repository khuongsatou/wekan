# REST API Plugin Token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure, separately revocable REST API token flow that lets a
plugin authenticate with `WEKAN_USER_ID` and `WEKAN_API_TOKEN`, while giving the
user and site admin clear UI for creation and revocation.

**Architecture:** Add a dedicated `apiTokens` collection whose records contain
only a SHA-256 hash, display prefix, owner, name, timestamps, and expiry. The
existing REST middleware will resolve this token before the legacy Meteor login
token path; the resolved `req.userId` is then consumed by existing REST route
permission checks. Member Settings will create/list/revoke the current user's
tokens, and Admin Panel > People will list metadata and revoke tokens for any
user without ever returning a secret.

**Tech Stack:** Meteor methods and WebApp middleware, Mongo collections,
Blaze/Jade templates, ReactiveVar, TAPi18n, Node built-in `crypto`, existing
Node test runner and Playwright test harness.

**Spec:** This plan is the approved working specification for the plugin REST
token feature requested on 2026-09-09.

## Global Constraints

- Never store or publish the raw token; show it exactly once after creation.
- Never use an MCP key (`wk_mcp_...`) as a REST/plugin token.
- Keep legacy Meteor login-token authentication working unchanged.
- A token inherits the owning user's existing WeKan permissions; it does not
  create a second permission system.
- Member Settings may manage only the signed-in user's tokens.
- Admin Panel management may inspect metadata and revoke tokens, but may never
  retrieve a token secret.
- Do not put secrets in URLs, logs, client publications, changelogs, or error
  messages.
- The plugin configuration must explicitly use `WEKAN_USER_ID` and
  `WEKAN_API_TOKEN`; no automatic conversion from an MCP key is allowed.
- Preserve unrelated dirty worktree changes already present before this task.

### Task 1: Define the token data contract and pure security helpers

**Files:**
- Create: `models/lib/apiTokens.js`
- Test: `tests/apiTokens.test.cjs`

**Interfaces:**
- Produces `API_TOKEN_PREFIX = 'wk_api_'`.
- Produces `API_TOKEN_EXPIRY_DAYS = [30, 90, 365]` and
  `MAX_ACTIVE_API_TOKENS_PER_USER = 10`.
- Produces `hashApiToken(value)`, `normalizeApiTokenName(value)`,
  `apiTokenExpiryDate(days, now)`, and `publicApiToken(doc)`.
- `publicApiToken` returns `_id`, `userId` only where needed by admin views,
  `name`, `prefix`, `createdAt`, `lastUsedAt`, `expiresAt`, and `revokedAt`,
  never `token`, `secret`, or `keyHash`.

- [ ] **Step 1: Write failing pure-logic tests**

  Test that hashing is deterministic and does not equal the raw value; names
  are trimmed, whitespace-collapsed, and limited to 80 characters; only 30,
  90, and 365 days produce dates; public output strips `keyHash` and secrets;
  and a `wk_mcp_...` value is not accepted by the REST-token verifier contract.

- [ ] **Step 2: Run the focused test and verify failure**

  Run: `node --test tests/apiTokens.test.cjs`

  Expected: FAIL because the new helper module and exported functions do not
  exist yet.

- [ ] **Step 3: Implement the pure helpers**

  Use `crypto.createHash('sha256').update(value).digest('hex')`. Generate no
  random value in this model-only module. Make expiry calculations accept an
  injected `now` so boundary tests do not depend on wall-clock time.

- [ ] **Step 4: Run the focused test and verify success**

  Run: `node --test tests/apiTokens.test.cjs`

  Expected: PASS, including the negative secret-leak assertions.

- [ ] **Step 5: Commit the self-contained helper change**

  Commit message: `Add REST API token data contract`

### Task 2: Add server-side token storage, verification, and lifecycle methods

**Files:**
- Create: `server/lib/apiTokens.js`
- Create: `server/apiTokens.js`
- Modify: `server/imports.js`
- Test: `tests/apiTokensServer.test.cjs`

**Interfaces:**
- `createApiToken(userId, name, expiresInDays, now)` returns
  `{ apiToken, token }`, where `apiToken` is the one-time secret and `token`
  is public metadata.
- `verifyApiToken(value, now)` returns `{ tokenId, userId }` or `null`.
- `listApiTokensForUser(userId)` returns public metadata only.
- `listApiTokensForAdmin()` returns public metadata plus the safe owner fields
  needed by the People table, never hashes or secrets.
- `revokeApiToken(requesterId, tokenId, { admin })` enforces owner/admin scope
  and returns `{ revoked: true, tokenId }`.
- Meteor methods are `apiTokens.listMine`, `apiTokens.createMine`,
  `apiTokens.revokeMine`, `apiTokens.adminList`, and `apiTokens.adminRevoke`.

- [ ] **Step 1: Write lifecycle and authorization tests**

  Cover successful creation, one-time raw secret return, hash-only persistence,
  10-active-token limit, invalid name/expiry, expired and revoked rejection,
  owner-only revoke, admin revoke, cross-user non-admin rejection, and public
  responses that contain no `keyHash` or raw token.

- [ ] **Step 2: Run the server test to verify failure**

  Run: `node --test tests/apiTokensServer.test.cjs`

  Expected: FAIL because the collection and lifecycle functions are missing.

- [ ] **Step 3: Implement collection, indexes, and lifecycle**

  Store records in `apiTokens` with `userId`, normalized `name`, `keyHash`,
  `prefix`, `createdAt`, `lastUsedAt`, `expiresAt`, and `revokedAt: null`.
  Add unique `keyHash`, owner/created-time, and expiry indexes during startup.
  Generate `wk_api_` plus cryptographically random entropy, update
  `lastUsedAt` at most once per five minutes, and enforce expiry/revocation at
  lookup time.

- [ ] **Step 4: Implement Meteor methods and admin authorization**

  Require a logged-in caller for all methods. Use the existing site-admin
  authorization helper used by Admin Panel People; do not trust an admin flag
  supplied by the client. Admin listing must join safe user display fields
  without publishing passwords, login tokens, or API-token hashes.

- [ ] **Step 5: Run the lifecycle tests to verify success**

  Run: `node --test tests/apiTokens.test.cjs tests/apiTokensServer.test.cjs`

  Expected: PASS.

- [ ] **Step 6: Commit the server lifecycle change**

  Commit message: `Add lifecycle management for REST API tokens`

### Task 3: Authenticate REST requests with dedicated plugin tokens

**Files:**
- Modify: `server/apiMiddleware.js`
- Modify: `server/lib/requestUser.js`
- Test: `tests/requestUserAuth.test.cjs`
- Test: `tests/apiTokenMiddleware.test.cjs`

**Interfaces:**
- `verifyApiToken` is called for `Authorization: Bearer wk_api_...` and
  `X-Auth-Token: wk_api_...` values.
- Successful verification sets `req.userId` and `req.apiTokenId`; legacy login
  tokens continue through their existing lookup path.
- `getUserIdFromRequest` accepts a dedicated API token for file/export routes as
  well as the already supported login-token forms.

- [ ] **Step 1: Add failing middleware tests**

  Assert that a valid `wk_api_...` Bearer token authenticates REST requests, an
  expired/revoked/wrong token returns no user, an MCP key is not accepted as a
  REST Bearer token, and a legacy login token still authenticates.

- [ ] **Step 2: Run focused middleware tests to verify failure**

  Run: `node --test tests/apiTokenMiddleware.test.cjs tests/requestUserAuth.test.cjs`

  Expected: FAIL for dedicated-token cases and PASS for unchanged legacy cases.

- [ ] **Step 3: Add dedicated-token resolution before legacy resolution**

  Parse the token once, recognize only the `wk_api_` prefix for this path, and
  resolve the token through `verifyApiToken`. Preserve the current MCP
  `x-api-key` branch and the current login-token Bearer/query behavior. Never
  let a failed dedicated-token lookup fall through in a way that treats an MCP
  key as a login token.

- [ ] **Step 4: Run middleware and regression tests**

  Run: `node --test tests/apiTokenMiddleware.test.cjs tests/requestUserAuth.test.cjs tests/apiLogout.test.cjs`

  Expected: PASS, with no changes to legacy logout semantics.

- [ ] **Step 5: Commit the authentication integration**

  Commit message: `Authenticate REST API with dedicated plugin tokens`

### Task 4: Add the Member Settings token tab

**Files:**
- Create: `client/components/settings/apiTokens.jade`
- Create: `client/components/settings/apiTokens.js`
- Create: `client/components/settings/apiTokens.css`
- Modify: `client/features/settings.js`
- Modify: `client/components/settings/peopleBody.jade`
- Modify: `client/components/settings/peopleBody.js`
- Modify: `models/lib/adminUrls.js`
- Modify: `config/router.js`
- Modify: `imports/i18n/data/en.i18n.json`
- Modify: `imports/i18n/data/vi.i18n.json`
- Test: `tests/apiTokensUi.test.cjs`

**Interfaces:**
- New People pane id: `api-tokens-setting`; URL slug:
  `/admin/people/api-tokens`.
- The pane calls `apiTokens.listMine`, `apiTokens.createMine`, and
  `apiTokens.revokeMine`.
- The create response displays `wk_api_...` once with Copy and Dismiss
  actions; after dismissal/reload only prefix and metadata remain.

- [ ] **Step 1: Extend routing/menu tests first**

  Assert that `api-tokens` maps to `api-tokens-setting`, the pane title and
  menu label use the same i18n key, and old People URLs still resolve.

- [ ] **Step 2: Run the routing/UI contract test to verify failure**

  Run: `node --test tests/apiTokensUi.test.cjs`

  Expected: FAIL because the route, menu item, and template do not exist.

- [ ] **Step 3: Register the pane and route**

  Add the pane to `ADMIN_PAGES.people.panes` and its title map, add the menu
  item near the existing Login/security-related entries, wire the active pane
  state and template branch in `peopleBody`, and import Jade/JS/CSS through the
  existing settings feature entry point.

- [ ] **Step 4: Build the token UI**

  Render name and expiry controls, token count, active/expired/revoked states,
  one-time secret reveal, copy feedback, and revoke confirmation. The copy
  button must copy only the secret; metadata rows must never contain the raw
  value. Include a concrete help block showing:

  ```text
  WEKAN_USER_ID=<your WeKan user id>
  WEKAN_API_TOKEN=<copy the token shown once after creation>
  ```

  Explain that `wk_mcp_...` is for MCP only and cannot be used as
  `WEKAN_API_TOKEN`.

- [ ] **Step 5: Add English and Vietnamese translations**

  Add keys for tab/title, description, name, expiry options, create/copy/revoke
  actions, one-time display warning, plugin environment variables, invalid
  token guidance, success/error states, and the MCP-vs-REST distinction. Keep
  key order aligned with `en.i18n.json`; do not overwrite unrelated human
  translations.

- [ ] **Step 6: Run contract tests and translation validation**

  Run: `node --test tests/apiTokensUi.test.cjs tests/adminUrls.test.cjs`

  Expected: PASS with the new pane active and all existing menu invariants
  intact. Run the repository's i18n tests afterward.

- [ ] **Step 7: Commit the Member Settings UI**

  Commit message: `Add Member Settings REST API token tab`

### Task 5: Add Admin Panel token metadata management

**Files:**
- Modify: `client/components/settings/peopleBody.jade`
- Modify: `client/components/settings/peopleBody.js`
- Modify: `client/components/settings/peopleBody.css`
- Modify: `server/apiTokens.js`
- Modify: `models/lib/adminUrls.js`
- Test: `tests/apiTokensAdmin.test.cjs`

**Interfaces:**
- Admin pane uses `apiTokens.adminList` and `apiTokens.adminRevoke`.
- Admin rows show owner username/display name, token name, prefix, created,
  last used, expiry, and status.
- Admin actions can revoke an active token but cannot reveal or copy its secret.

- [ ] **Step 1: Write admin negative tests**

  Assert that a non-site-admin cannot call admin list/revoke, an admin can see
  metadata for multiple owners, the raw secret and hash are absent, and revoking
  a token immediately causes the REST middleware to reject it.

- [ ] **Step 2: Run the admin test to verify failure**

  Run: `node --test tests/apiTokensAdmin.test.cjs`

  Expected: FAIL because admin methods and rows are not wired.

- [ ] **Step 3: Wire admin listing and revoke action**

  Reuse the existing People table/menu conventions and confirmation pattern.
  Add server-side owner filtering/pagination if the existing People dataset is
  large; never fetch all token secrets to the browser.

- [ ] **Step 4: Run admin and lifecycle tests**

  Run: `node --test tests/apiTokensAdmin.test.cjs tests/apiTokensServer.test.cjs`

  Expected: PASS.

- [ ] **Step 5: Commit the admin management change**

  Commit message: `Add admin management for REST API token metadata`

### Task 6: Document plugin configuration and verify end-to-end behavior

**Files:**
- Modify: `tools/ai-systems-mcp/README.md`
- Modify: `refer/MCP_INTEGRATION_TEMPLATE.md`
- Modify: `docs/Features/Admin-Panel/Settings/README.md` or the existing
  Member Settings documentation location identified during implementation
- Test: `tests/apiTokenE2E.test.cjs`
- Test: `tests/playwright/api-tokens.spec.js`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Plugin docs distinguish REST configuration from MCP configuration:

  ```text
  WEKAN_URL=https://wekan.example.com
  WEKAN_USER_ID=<user id that owns the token>
  WEKAN_API_TOKEN=wk_api_...
  ```

- MCP remains configured with `wk_mcp_...` and `x-api-key`; no docs imply the
  two token types are interchangeable.

- [ ] **Step 1: Add an end-to-end auth test**

  Create a fixture user and token, call a harmless authenticated REST endpoint,
  assert the user identity is honored, revoke the token, and assert the same
  request is rejected. Assert that no test output prints the raw token.

- [ ] **Step 2: Add Playwright coverage**

  Cover opening `/admin/people/api-tokens`, creating a token, seeing the
  one-time reveal, copying/dismissing it, confirming metadata-only display after
  reload, revoking it, and verifying that a second user cannot see the first
  user's Member Settings tokens. Cover Admin Panel metadata and revoke access.

- [ ] **Step 3: Update plugin and user documentation**

  State that `WEKAN_USER_ID` is mandatory for the plugin, `WEKAN_API_TOKEN`
  must be a `wk_api_...` token created in the new tab, and `wk_mcp_...` keys are
  only for the MCP HTTP service. Include rotation/revocation instructions and
  warn against placing secrets in source control or logs.

- [ ] **Step 4: Add the Upcoming changelog entry**

  Add a WeKan-format feature entry under `# Upcoming WeKan ® release` with the
  implementation commit link after the feature commit exists. Keep the entry
  grouped with authentication/integration features and mention one-time secret
  display, hash-only storage, owner permissions, and admin metadata revoke.

- [ ] **Step 5: Run the full verification set**

  Run:

  ```bash
  node --test tests/apiTokens.test.cjs tests/apiTokensServer.test.cjs \
    tests/apiTokenMiddleware.test.cjs tests/apiTokensAdmin.test.cjs \
    tests/apiTokensUi.test.cjs tests/apiTokenE2E.test.cjs
  npm test -- --runInBand
  npm run test:playwright -- --grep "API token"
  ```

  Expected: all focused tests pass; existing REST, MCP, login, and Admin Panel
  tests remain green. If the full Meteor/Playwright stack is unavailable, record
  exactly which commands were blocked and retain the unit/contract evidence.

- [ ] **Step 6: Commit documentation and verification coverage**

  Commit message: `Document and verify REST API plugin tokens`

## Self-review checklist

- The plan covers creation, storage, authentication, Member Settings, Admin
  Panel, plugin configuration, revocation, translations, docs, and tests.
- It explicitly rejects MCP keys as REST tokens and preserves legacy login-token
  behavior.
- Every secret-bearing path has a one-time display or a negative leak test.
- Admin access is server-enforced; client visibility is not treated as a guard.
- No implementation depends on an external translation service or new secret.
- Existing dirty worktree changes are outside the listed modifications and must
  remain untouched.
