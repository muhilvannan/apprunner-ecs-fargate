const express = require('express');
const fs = require('fs');
const path = require('path');
const { ServiceDiscoveryClient, DiscoverInstancesCommand } = require('@aws-sdk/client-servicediscovery');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
app.use(express.json());

const WORKSPACE_ID = process.env.WORKSPACE_ID || 'ws-unknown';
const BASE_PATH    = process.env.BASE_PATH || `/workspace${WORKSPACE_ID}`;
const DOMAIN       = process.env.DOMAIN || 'builder.muhilvannan.com';
const PORT         = 3001;

// ---------------------------------------------------------------------------
// Cloud Map SDK setup (D-06)
// ---------------------------------------------------------------------------
const sdClient = new ServiceDiscoveryClient({ region: process.env.AWS_DEFAULT_REGION || process.env.AWS_REGION || 'eu-west-1' });
const CLOUDMAP_NAMESPACE = 'workspace-discovery.local';

// ---------------------------------------------------------------------------
// Per-workspace Cloud Map cache (D-07)
// Cache: { [workspaceId]: { instances: [], fetchedAt: 0 } }
// ---------------------------------------------------------------------------
const cloudMapCache = {};
const CACHE_TTL_MS = 5000;

// Proxy instance cache keyed by "appId:target" — reused across requests to
// avoid creating new EventEmitter listeners on every request (MaxListeners warning)
const proxyInstanceCache = {};

async function resolveCloudMap(workspaceId, appId) {
  const now = Date.now();
  const cached = cloudMapCache[workspaceId];
  let instances;

  if (cached && (now - cached.fetchedAt) < CACHE_TTL_MS) {
    instances = cached.instances;
  } else {
    const resp = await sdClient.send(new DiscoverInstancesCommand({
      NamespaceName: CLOUDMAP_NAMESPACE,
      ServiceName: `${workspaceId}-apps`,
      HealthStatus: 'HEALTHY',
      MaxResults: 100,
    }));
    instances = resp.Instances || [];
    cloudMapCache[workspaceId] = { instances, fetchedAt: now };
  }

  const match = instances.find(i => i.Attributes?.app_id === appId);
  if (!match) return null;
  return {
    ip: match.Attributes.AWS_INSTANCE_IPV4,
    port: match.Attributes.AWS_INSTANCE_PORT,
    appType: match.Attributes.app_type || 'custom',
  };
}

// ---------------------------------------------------------------------------
// Proxy: /workspace{workspaceId}/{appId}/* → app task via Cloud Map
// LP-01, LP-04, D-05: registered before hub routes; pathRewrite strips prefix
// ---------------------------------------------------------------------------
app.use(`${BASE_PATH}/:appId`, async (req, res, next) => {
  const appId = req.params.appId;
  // Don't proxy internal endpoints
  if (appId === 'internal') return next();

  // Redirect bare app root (no trailing slash) so relative assets resolve correctly
  // e.g. /workspace23456/app-2 → /workspace23456/app-2/
  if (req.originalUrl === `${BASE_PATH}/${appId}`) {
    return res.redirect(301, `${BASE_PATH}/${appId}/`);
  }

  let target;
  let appType = 'custom';
  try {
    const resolved = await resolveCloudMap(WORKSPACE_ID, appId);
    if (!resolved) {
      return res.status(503).json({ error: 'App not available', appId, workspaceId: WORKSPACE_ID });
    }
    target = `http://${resolved.ip}:${resolved.port}`;
    appType = resolved.appType || 'custom';
  } catch (err) {
    console.error(`[proxy] Cloud Map lookup failed for ${appId}:`, err.message);
    return res.status(503).json({ error: 'Service discovery failed', appId });
  }

  const cacheKey = `${appId}:${target}`;
  if (!proxyInstanceCache[cacheKey]) {
    // Streamlit uses --server.baseUrlPath so it expects the full prefixed path.
    // Other app types handle the stripped path themselves.
    const pathRewrite = appType === 'streamlit'
      ? undefined
      : { [`^${BASE_PATH}/${appId}`]: '' };
    proxyInstanceCache[cacheKey] = createProxyMiddleware({
      target,
      changeOrigin: true,
      ws: true,
      ...(pathRewrite && { pathRewrite }),
      on: {
        error: (proxyErr, _req, proxyRes) => {
          console.error(`[proxy] Error forwarding ${appId}:`, proxyErr.message);
          if (proxyRes && !proxyRes.headersSent) {
            proxyRes.status(502).json({ error: 'Upstream error' });
          }
        },
      },
    });
  }
  proxyInstanceCache[cacheKey](req, res, next);
});

// ---------------------------------------------------------------------------
// Internal routes API — live Cloud Map query (LP-05, D-08)
// Registered under BASE_PATH so it routes through the ALB /workspace{id}/* rule
// ---------------------------------------------------------------------------
app.get(`${BASE_PATH}/internal/routes`, async (req, res) => {
  try {
    const resp = await sdClient.send(new DiscoverInstancesCommand({
      NamespaceName: CLOUDMAP_NAMESPACE,
      ServiceName: `${WORKSPACE_ID}-apps`,
      HealthStatus: 'HEALTHY',
      MaxResults: 100,
    }));
    const apps = (resp.Instances || []).map(i => ({
      appId: i.Attributes?.app_id,
      ip: i.Attributes?.AWS_INSTANCE_IPV4,
      port: i.Attributes?.AWS_INSTANCE_PORT,
      instanceId: i.InstanceId,
    }));
    res.json({ workspaceId: WORKSPACE_ID, apps });
  } catch (err) {
    console.error('[internal/routes] Cloud Map query failed:', err.message);
    res.status(503).json({ error: 'Could not query Cloud Map', detail: err.message });
  }
});

// ---------------------------------------------------------------------------
// Health check (used by ALB)
// ---------------------------------------------------------------------------
app.get('/healthz', (req, res) => {
  res.json({ status: 'ok', workspaceId: WORKSPACE_ID });
});

// ---------------------------------------------------------------------------
// Workspace hub UI — serve index.html with injected context
// ---------------------------------------------------------------------------
app.get(`${BASE_PATH}`, (req, res) => {
  serveHub(res);
});

app.get(`${BASE_PATH}/`, (req, res) => {
  serveHub(res);
});

app.get('/', (req, res) => {
  serveHub(res);
});

function serveHub(res) {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8')
    .replaceAll('__WORKSPACE_ID__', WORKSPACE_ID)
    .replaceAll('__BASE_PATH__', BASE_PATH)
    .replaceAll('__DOMAIN__', DOMAIN);
  res.type('html').send(html);
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
const server = app.listen(PORT, () => {
  console.log(`[landing-page] Workspace ${WORKSPACE_ID} hub listening on port ${PORT}`);
  console.log(`[landing-page] BASE_PATH=${BASE_PATH}  DOMAIN=${DOMAIN}`);
});

// WebSocket upgrade handler — ALB passes TCP upgrade through to backend
server.on('upgrade', async (req, socket, head) => {
  const url = req.url || '';
  console.log(`[ws] upgrade request: ${url}`);

  const match = url.match(new RegExp(`^${BASE_PATH.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/([^/]+)`));
  if (!match) { socket.destroy(); return; }
  const appId = match[1];
  if (appId === 'internal') { socket.destroy(); return; }

  try {
    const resolved = await resolveCloudMap(WORKSPACE_ID, appId);
    if (!resolved) {
      console.error(`[ws] No Cloud Map instance for ${appId}`);
      socket.destroy();
      return;
    }
    const target = `http://${resolved.ip}:${resolved.port}`;
    console.log(`[ws] upgrading ${appId} → ${target}`);

    const cacheKey = `${appId}:${target}`;
    if (!proxyInstanceCache[cacheKey]) {
      const pathRewrite = resolved.appType === 'streamlit'
        ? undefined
        : { [`^${BASE_PATH}/${appId}`]: '' };
      proxyInstanceCache[cacheKey] = createProxyMiddleware({
        target,
        changeOrigin: true,
        ws: true,
        ...(pathRewrite && { pathRewrite }),
      });
    }
    proxyInstanceCache[cacheKey].upgrade(req, socket, head);
  } catch (err) {
    console.error(`[ws] upgrade failed for ${appId}:`, err.message);
    socket.destroy();
  }
});
