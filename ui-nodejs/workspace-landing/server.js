const express = require('express');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const app = express();
app.use(express.json());

const WORKSPACE_ID    = process.env.WORKSPACE_ID || 'ws-unknown';
const BASE_PATH       = process.env.BASE_PATH || `/workspace${WORKSPACE_ID}`;
const DOMAIN          = process.env.DOMAIN || 'builder.muhilvannan.com';
const ENVOY_ADMIN_PORT = parseInt(process.env.ENVOY_ADMIN_PORT || '9901');
const PORT            = 3001;
const ENVOY_CONFIG    = '/etc/envoy/envoy.yaml';

// ---------------------------------------------------------------------------
// In-memory route table: { [appId]: { appIP, port, basePath } }
// ---------------------------------------------------------------------------
const routes = {};

// ---------------------------------------------------------------------------
// Envoy config generation
// ---------------------------------------------------------------------------
function buildEnvoyConfig() {
  const routeEntries = Object.entries(routes);

  // Build per-app route + cluster entries
  const appRoutes = routeEntries.map(([appId, { basePath }]) => `
              - match:
                  prefix: "${basePath}/"
                route:
                  cluster: app_${appId}
                  prefix_rewrite: "/"
              - match:
                  prefix: "${basePath}"
                route:
                  cluster: app_${appId}
                  prefix_rewrite: "/"`).join('');

  const appClusters = routeEntries.map(([appId, { appIP, port }]) => `
  - name: app_${appId}
    connect_timeout: 5s
    type: STATIC
    load_assignment:
      cluster_name: app_${appId}
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: "${appIP}"
                port_value: ${port}`).join('');

  return `static_resources:
  listeners:
  - name: listener_0
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8080
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          codec_type: AUTO
          route_config:
            name: local_route
            virtual_hosts:
            - name: workspace_${WORKSPACE_ID}
              domains: ["*"]
              routes:${appRoutes}
              - match:
                  prefix: "${BASE_PATH}"
                route:
                  cluster: landing_page
              - match:
                  prefix: "/"
                route:
                  cluster: landing_page
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
  clusters:
  - name: landing_page
    connect_timeout: 5s
    type: STATIC
    load_assignment:
      cluster_name: landing_page
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: "127.0.0.1"
                port_value: ${PORT}${appClusters}

admin:
  address:
    socket_address:
      address: 0.0.0.0
      port_value: ${ENVOY_ADMIN_PORT}
`;
}

function writeEnvoyConfig() {
  const config = buildEnvoyConfig();
  fs.mkdirSync(path.dirname(ENVOY_CONFIG), { recursive: true });
  fs.writeFileSync(ENVOY_CONFIG, config, 'utf8');
  console.log(`[envoy-config] Written: ${Object.keys(routes).length} app route(s)`);
}

function reloadEnvoy() {
  try {
    // Signal Envoy to reload config via SIGHUP
    const pid = execSync('pidof envoy 2>/dev/null || true').toString().trim();
    if (pid) {
      execSync(`kill -SIGHUP ${pid}`);
      console.log(`[envoy-reload] SIGHUP sent to envoy PID ${pid}`);
    } else {
      console.log('[envoy-reload] Envoy not running yet — config written for startup');
    }
  } catch (e) {
    console.warn('[envoy-reload] Could not signal envoy:', e.message);
  }
}

// Write initial config on startup (landing page only, no app routes yet)
writeEnvoyConfig();

// ---------------------------------------------------------------------------
// Internal routes API (called by controller)
// ---------------------------------------------------------------------------

// GET /internal/routes — return current route map
app.get('/internal/routes', (req, res) => {
  res.json({ routes, workspaceId: WORKSPACE_ID });
});

// POST /internal/routes/add — add/update an app route
app.post('/internal/routes/add', (req, res) => {
  const { appId, appIP, port, basePath } = req.body;
  if (!appId || !appIP || !port) {
    return res.status(400).json({ error: 'appId, appIP, port required' });
  }
  routes[appId] = { appIP, port, basePath: basePath || `${BASE_PATH}/${appId}` };
  console.log(`[routes] Added: ${appId} → ${appIP}:${port}`);
  writeEnvoyConfig();
  reloadEnvoy();
  res.json({ ok: true, appId, routes });
});

// POST /internal/routes/remove — remove an app route
app.post('/internal/routes/remove', (req, res) => {
  const { appId } = req.body;
  if (!appId) {
    return res.status(400).json({ error: 'appId required' });
  }
  delete routes[appId];
  console.log(`[routes] Removed: ${appId}`);
  writeEnvoyConfig();
  reloadEnvoy();
  res.json({ ok: true, appId, routes });
});

// ---------------------------------------------------------------------------
// Health check (used by Envoy and ALB)
// ---------------------------------------------------------------------------
app.get('/healthz', (req, res) => {
  res.json({ status: 'ok', workspaceId: WORKSPACE_ID, routes: Object.keys(routes) });
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
    .replace('__WORKSPACE_ID__', WORKSPACE_ID)
    .replace('__BASE_PATH__', BASE_PATH)
    .replace('__DOMAIN__', DOMAIN);
  res.type('html').send(html);
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
app.listen(PORT, () => {
  console.log(`[landing-page] Workspace ${WORKSPACE_ID} hub listening on port ${PORT}`);
  console.log(`[landing-page] BASE_PATH=${BASE_PATH}  DOMAIN=${DOMAIN}`);
});
