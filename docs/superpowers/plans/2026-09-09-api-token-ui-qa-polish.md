# API Token UI QA and Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify the REST API token page in a real browser at desktop and mobile widths, then fix layout, states, and navigation issues until the page matches WeKan's existing UI patterns.

**Architecture:** Keep the existing `apiTokenSettings` Blaze template and route. Polish its outer page shell and internal panels in the feature CSS, reuse the MCP hub and Admin Panel layout conventions, and validate both the standalone user route and the admin People pane. Do not change token storage or authentication semantics unless UI testing exposes a concrete integration defect.

**Tech Stack:** Meteor 3.5, Blaze/Jade templates, CSS, Playwright, CUA browser screenshots, Node test scripts.

**Spec:** `docs/superpowers/plans/2026-09-09-rest-api-plugin-token.md`

## Global Constraints

- Keep REST tokens separate from `wk_mcp_...` MCP keys.
- Never display a stored token secret again after the one-time reveal is dismissed.
- Preserve the existing routes `/api-tokens` and `/admin/people/api-tokens`.
- Preserve Vietnamese and English i18n keys and current security copy.
- Do not use production data for browser QA; use the local Meteor database and a disposable local account.
- Do not commit or publish from contributor mode; inspect git identity before any commit.

---

### Task 1: Establish a browser QA baseline

**Files:**
- Read: `config/router.js:689-725`
- Read: `client/components/settings/apiTokens.jade`
- Read: `client/components/settings/apiTokens.css`
- Read: `client/components/main/mcpHub.jade`
- Read: `client/components/main/mcpHub.css`
- Test: `tests/playwright/specs/50-api-tokens.e2e.js`

**Interfaces:**
- Consumes: the existing local Meteor route and `apiTokenSettings` template.
- Produces: a written baseline of expected selectors, screenshots, and layout defects for Tasks 2–5.

- [ ] **Step 1: Start the local browser target.**

  Run the local WeKan instance with the dev database and a writable path:

  ```bash
  MONGO_URL='mongodb://127.0.0.1:3011/wekan?replicaSet=meteor' \
  MONGO_OPLOG_URL='mongodb://127.0.0.1:3011/local?replicaSet=meteor' \
  WITH_API=true WRITABLE_PATH="$PWD/.meteor/local/build" \
  ./.tools/.meteor/meteor run --port 2000
  ```

- [ ] **Step 2: Open the real page and capture the desktop baseline.**

  Open `http://localhost:2000/api-tokens`, sign in with a disposable local user, and capture the page at the browser's default desktop viewport. Record whether the header, page margin, panel width, form controls, token list, and plugin configuration block are visible without horizontal overflow.

- [ ] **Step 3: Capture responsive baselines.**

  Repeat at 1024px, 768px, and 390px viewport widths. Record any overlap, clipped text, controls wider than the viewport, unreadable token metadata, or buttons that become inaccessible.

- [ ] **Step 4: Compare against the MCP hub.**

  Open `/mcp` at the same widths and use its `.mcp-hub-page` and `.mcp-hub-panel` behavior as the visual reference. Do not copy unrelated MCP-specific content or colors into the token feature.

---

### Task 2: Add deterministic UI regression coverage

**Files:**
- Modify: `tests/playwright/specs/50-api-tokens.e2e.js`
- Test data: local disposable account created by the test fixture or precondition helper already used by the Playwright suite.

**Interfaces:**
- Consumes: labels and classes from `client/components/settings/apiTokens.jade`.
- Produces: assertions that fail when the page is unstyled, clipped, or functionally incomplete.

- [ ] **Step 1: Assert the standalone page shell.**

  Add assertions for:

  ```js
  await expect(page.getByRole('region', { name: 'REST API Tokens' })).toBeVisible();
  await expect(page.locator('.api-token-page')).toBeVisible();
  await expect(page.locator('.api-token-panel')).toHaveCount(3);
  ```

  Use the Vietnamese equivalents when the fixture selects Vietnamese, or make the test language-independent by asserting the stable class and accessible region.

- [ ] **Step 2: Assert no horizontal overflow at supported widths.**

  For each viewport in `[1440, 1024, 768, 390]`, assert `document.documentElement.scrollWidth <= window.innerWidth` and assert the create form, expiry select, and submit button are visible.

- [ ] **Step 3: Assert create and one-time reveal behavior.**

  Fill `Tên token` with `Playwright UI QA`, select `90`, submit, assert the status region and `wk_api_` prefix are visible, then dismiss the reveal and assert the secret input is no longer visible while the token remains in the list.

- [ ] **Step 4: Assert revoke behavior.**

  Revoke the disposable token, accept the confirmation dialog, and assert the row changes to the revoked state or disappears according to the current implementation. Do not assert a secret value.

- [ ] **Step 5: Run the focused test and confirm it fails for a deliberately missing layout selector before the CSS fix.**

  Run:

  ```bash
  npx playwright test tests/playwright/specs/50-api-tokens.e2e.js
  ```

  Expected before the fix: the functional checks may pass, but the shell/overflow assertion identifies the layout defect.

---

### Task 3: Polish the standalone token page layout

**Files:**
- Modify: `client/components/settings/apiTokens.css`
- Read: `client/components/main/mcpHub.css`

**Interfaces:**
- Consumes: the existing `.api-token-page`, `.api-token-heading`, `.api-token-panel`, `.api-token-list`, and `.api-token-row` classes.
- Produces: a responsive page shell with consistent spacing, panel styling, readable controls, and no viewport overflow.

- [ ] **Step 1: Add the page shell.**

  Define `.api-token-page` with `box-sizing: border-box`, centered `max-width: 1100px`, `padding: 28px`, and an `18px` vertical grid gap, matching the MCP page shell.

- [ ] **Step 2: Style heading and panels consistently.**

  Apply the existing MCP visual language to `.api-token-heading` and `.api-token-panel`: reset first-child margins, use the translucent white background, subtle border, rounded corners, shadow, and consistent panel padding.

- [ ] **Step 3: Make form controls resilient.**

  Keep the form as a single-column grid, cap text/select controls at `760px`, set `width: 100%` with `box-sizing: border-box`, and ensure the submit button does not exceed the panel or viewport.

- [ ] **Step 4: Make token rows responsive.**

  Keep the desktop row readable with named token, prefix, dates, state, and action; at `800px` and below switch to one column, allow long prefixes/configuration text to wrap or scroll locally, and keep the revoke button reachable.

- [ ] **Step 5: Reload the browser after HMR and inspect all four widths.**

  Confirm the page has a visible margin from the header, panels are centered, labels and controls align, and no horizontal scrollbar appears.

---

### Task 4: Verify user and admin navigation surfaces

**Files:**
- Read: `config/router.js:689-725`
- Read: `client/components/users/userHeader.jade:29-36`
- Read: `client/components/settings/peopleBody.jade:24-33`
- Read: `client/components/settings/peopleBody.js:433`
- Read: `models/lib/adminUrls.js:60-80`
- Test: `tests/apiTokensUi.test.cjs`

**Interfaces:**
- Consumes: the standalone route and the admin pane mapping.
- Produces: verified navigation evidence for `/api-tokens` and `/admin/people/api-tokens` without changing route contracts.

- [ ] **Step 1: Verify the user menu link.**

  From the signed-in local account, open the member menu and confirm the API token item navigates to `/api-tokens` and renders the same polished page shell.

- [ ] **Step 2: Verify the admin pane.**

  Sign in as a disposable local admin, open `/admin/people/api-tokens`, and confirm the People left menu highlights the API token pane, the admin title renders, and the standalone user-only create/configuration sections are not shown in admin mode.

- [ ] **Step 3: Run static route/UI checks.**

  ```bash
  node tests/apiTokensUi.test.cjs
  ```

  Expected: all route, template, and menu assertions pass.

---

### Task 5: Final verification and browser evidence

**Files:**
- Verify: `client/components/settings/apiTokens.css`
- Verify: `tests/playwright/specs/50-api-tokens.e2e.js`
- Evidence: local browser tab at `http://localhost:2000/api-tokens`

**Interfaces:**
- Consumes: the polished UI and regression tests from Tasks 2–4.
- Produces: passing verification results and screenshots of the actual web UI.

- [ ] **Step 1: Run the complete relevant checks.**

  ```bash
  node tests/apiTokensUi.test.cjs
  npm run test:unit:node
  npx playwright test tests/playwright/specs/50-api-tokens.e2e.js
  git diff --check
  ```

  Expected: all focused UI, unit, browser, and whitespace checks pass. If Playwright cannot connect to the local server, report that limitation instead of substituting a mock screenshot.

- [ ] **Step 2: Capture final screenshots.**

  Capture one desktop screenshot showing the WeKan header, page heading, create-token panel, expiry control, and token list; capture one mobile screenshot showing the stacked layout and reachable controls. Do not include a real production secret. If a disposable token is created for the screenshot, crop or dismiss the one-time secret before delivery.

- [ ] **Step 3: Confirm no production side effect.**

  Verify the browser URL is `localhost:2000`, the test account is disposable, and no production tab or production database was modified.

- [ ] **Step 4: Review the diff before handoff.**

  ```bash
  git status --short
  git diff -- client/components/settings/apiTokens.css tests/playwright/specs/50-api-tokens.e2e.js
  ```

  Confirm that only the UI polish and its tests are included; leave unrelated worktree changes untouched.

