// API middleware: body parsing, auth token handling, API gate, and JSON response helper.
// Replaces communitypackages:json-routes middleware chain.
// Must be imported before model files that register API routes.

const { Meteor } = require('meteor/meteor');
const { Accounts } = require('meteor/accounts-base');
const { WebApp } = require('meteor/webapp');
const bodyParser = require('body-parser');
const { safeJsonStringify } = require('/server/lib/apiResponseHelpers');
const { verifyMcpApiKey } = require('/server/lib/mcpApiKeys');
const { API_TOKEN_PREFIX, verifyApiToken } = require('/server/lib/apiTokens');

// ---------------------------------------------------------------------------
// 1. Body parsing (previously registered by json-routes)
// ---------------------------------------------------------------------------
WebApp.handlers.use(bodyParser.urlencoded({ limit: '50mb', extended: false }));
WebApp.handlers.use(bodyParser.json({ limit: '50mb' }));

// ---------------------------------------------------------------------------
// 2. API gate — check WITH_API env var (previously in models/users.js)
// ---------------------------------------------------------------------------
WebApp.handlers.use(function apiGate(req, res, next) {
  const api = req.url.startsWith('/api');
  if ((api && process.env.WITH_API === 'true') || !api) {
    return next();
  }
  res.writeHead(301, { Location: '/' });
  return res.end();
});

// ---------------------------------------------------------------------------
// 3. Bearer token parser (replaces communitypackages:rest-bearer-token-parser)
// ---------------------------------------------------------------------------
WebApp.handlers.use(function parseBearerToken(req, res, next) {
  // Check Authorization header first
  const authHeader = req.headers.authorization;
  if (authHeader) {
    const match = authHeader.match(/^Bearer\s+(.+)$/i);
    if (match) {
      req.authToken = match[1];
    }
  }

  // Legacy clients may still use access_token in the query string. Dedicated
  // REST tokens are header-only: a wk_api_... value in a URL can be copied to
  // proxy/access logs and must never become an authenticated request.
  if (!req.authToken && req.query && req.query.access_token) {
    const accessToken = req.query.access_token;
    if (typeof accessToken !== 'string' || !accessToken.startsWith(API_TOKEN_PREFIX)) {
      req.authToken = accessToken;
    }
  }

  if (!req.authToken) {
    const xAuthToken = req.headers['x-auth-token'] || req.headers['X-Auth-Token'];
    if (typeof xAuthToken === 'string' && xAuthToken) {
      req.authToken = xAuthToken;
    }
  }

  next();
});

// MCP integration keys are independent from browser/login tokens. The raw key
// is never stored: verifyMcpApiKey hashes it and resolves only active,
// unexpired records. Authorization: Bearer is still handled by the existing
// login-token path below; MCP clients should prefer x-api-key.
WebApp.handlers.use(async function authenticateByMcpApiKey(req, res, next) {
  const apiKey = req.headers['x-api-key'];
  if (typeof apiKey === 'string' && apiKey) {
    try {
      const verified = await verifyMcpApiKey(apiKey);
      if (verified) {
        req.userId = verified.userId;
        req.mcpApiKeyId = verified.keyId;
        req.mcpApiKeyScopes = verified.scopes;
        if (
          !verified.scopes.includes('mcp-tools:call') ||
          req.method === 'DELETE'
        ) {
          sendJsonResult(res, {
            code: 403,
            data: { ok: false, error: 'MCP API key operation not permitted' },
          });
          return;
        }
      }
    } catch (error) {
      // Routes answer 401 from their normal permission checks.
    }
  }
  next();
});

// ---------------------------------------------------------------------------
// 4. User authentication (replaces communitypackages:authenticate-user-by-token)
// ---------------------------------------------------------------------------
WebApp.handlers.use(async function authenticateByToken(req, res, next) {
  if (req.authToken && !req.userId) {
    try {
      const apiToken = await verifyApiToken(req.authToken);
      if (apiToken) {
        req.userId = apiToken.userId;
        req.apiTokenId = apiToken.tokenId;
        return next();
      }
      const hashedToken = Accounts._hashLoginToken(req.authToken);
      const user = await Meteor.users.findOneAsync(
        { 'services.resume.loginTokens.hashedToken': hashedToken },
        { fields: { _id: 1 } },
      );
      if (user) {
        req.userId = user._id;
      }
    } catch (e) {
      // Ignore auth errors — routes handle missing userId themselves
    }
  }
  next();
});

// ---------------------------------------------------------------------------
// 5. sendJsonResult — drop-in replacement for JsonRoutes.sendResult
// ---------------------------------------------------------------------------
function sendJsonResult(res, options) {
  options = options || {};

  // Default response headers (matching json-routes behavior)
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Pragma', 'no-cache');

  // Custom headers
  if (options.headers) {
    Object.entries(options.headers).forEach(function ([key, value]) {
      res.setHeader(key, value);
    });
  }

  // Status code
  res.statusCode = options.code || 200;

  // JSON body
  if (options.data !== undefined) {
    const shouldPrettyPrint = process.env.NODE_ENV === 'development';
    const spacer = shouldPrettyPrint ? 2 : null;
    res.setHeader('Content-Type', 'application/json');
    // Use a crash-proof serializer: some error payloads (e.g. a circular
    // SimpleSchema validation error) would otherwise throw inside
    // JSON.stringify and surface as a generic HTTP 500. See #5804.
    res.write(safeJsonStringify(options.data, spacer));
  }

  res.end();
}

function redactAuthQuery(url) {
  if (typeof url !== 'string' || !url) return 'a request';
  try {
    const parsed = new URL(url, 'http://wekan.invalid');
    for (const key of ['access_token', 'authToken']) {
      if (parsed.searchParams.has(key)) parsed.searchParams.set(key, '<redacted>');
    }
    return `${parsed.pathname}${parsed.search}`;
  } catch (_) {
    return '[unparseable request URL]';
  }
}

// GHSA-3gcg-g6rf-w2rx: an export route that throws must not escape as an unhandled
// promise rejection. This app turns one of those into a full process crash - the
// note in server/ldapGroupSync.js explains why - so a single crafted request could
// take the server down for everyone. Every route body wrapped in this answers with a
// 500 instead, and the request that caused it is logged.
//
// The guards inside the handlers are still the real fix; this is the net under them,
// so the next missing null check is one broken request rather than an outage.
function safeRoute(handler) {
  return async function safeRouteHandler(req, res, ...rest) {
    try {
      return await handler.call(this, req, res, ...rest);
    } catch (error) {
      console.error('[api] unhandled error while serving',
        redactAuthQuery(req && req.url), error);
      try {
        if (!res.headersSent) {
          res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
        }
        res.end('Internal server error');
      } catch (_) {
        // The response is already gone; nothing left to answer with.
      }
      return undefined;
    }
  };
}

module.exports = { sendJsonResult, safeRoute };
