# ADR-003: Reverse Proxy Path Rewriting and WebSocket Handling

**Status:** Accepted
**Date:** 2026-03-31

---

## Context

When a reverse proxy sits in front of applications, it receives requests at a prefixed path
(e.g. `/workspace{id}/{appId}/some/page`) and must forward them to an upstream that serves
content from its root (`/some/page`). This creates two classes of problem:

1. **Path rewriting** — the proxy must strip the workspace/app prefix before forwarding
2. **Asset resolution** — apps generate URLs for their own assets; those URLs must remain
   valid when accessed through the proxy
3. **WebSocket upgrades** — applications using WebSockets (e.g. Streamlit, live-reload tools)
   require the proxy to handle the HTTP → WS upgrade handshake explicitly

---

## Decisions

### D-01: Strip the path prefix at the proxy, not the application

The proxy uses `pathRewrite` to strip the full workspace+app prefix before forwarding to the
upstream. The upstream app is started **without any base path configuration** and serves from `/`.

**Why:** Configuring each app type with the correct base path would require passing
workspace/app IDs into every container startup command and keeping them in sync with the proxy
routing rules. Stripping at the proxy is a single point of change and works for any app type
without app-level configuration.

**Consequence:** Apps must not embed their own base path in asset URLs. If an app framework
requires a `--base-url` or `--root-path` flag to generate correct internal links, that flag
must be set to `/` (or omitted entirely).

**Anti-pattern avoided:** Setting `--server.baseUrlPath=/workspace{id}/{appId}` on Streamlit —
this causes the app to expect requests at the prefixed path but the proxy strips it, resulting
in 404s.

---

### D-02: Enforce trailing slash on app root to fix relative asset resolution

When a browser loads `/workspace{id}/{appId}` (no trailing slash), it treats the base URL as
`/workspace{id}/` — one level up — and resolves relative asset paths (e.g. `./assets/main.css`)
against that, producing `/workspace{id}/assets/main.css` instead of
`/workspace{id}/{appId}/assets/main.css`.

The proxy issues a `301` redirect from `/workspace{id}/{appId}` to `/workspace{id}/{appId}/`
before proxying. Once the browser is at the slash-terminated URL, relative paths resolve
correctly within the app prefix.

**Why not rewrite URLs in the HTML:** Rewriting asset URLs in proxied HTML responses requires
inspecting and mutating response bodies, which is fragile, breaks streaming, and fails for
JS-generated dynamic URLs.

---

### D-03: Handle WebSocket upgrades explicitly in the proxy server

HTTP proxying and WebSocket proxying are separate at the TCP level. An HTTP reverse proxy does
not automatically forward WebSocket upgrade requests — the server must listen for the `upgrade`
event and route it separately.

The landing page server:
1. Listens for `upgrade` events on the raw HTTP server instance
2. Extracts the `appId` from the request URL
3. Resolves the upstream target from Cloud Map
4. Forwards the upgrade using the proxy middleware's `.upgrade()` handler with the same
   `pathRewrite` rule as HTTP requests

**Why this matters for Streamlit:** Streamlit's UI communicates exclusively over a persistent
WebSocket (`/_stcore/stream`). Without explicit upgrade proxying, the page loads but the app
never becomes interactive — the browser shows a blank spinner or connection error.

**Generalisation:** Any app using WebSockets (Streamlit, Jupyter, hot-reload dev servers, etc.)
requires this pattern. The path rewrite must be applied identically to both HTTP and WS traffic,
otherwise the upstream sees mismatched paths.

---

## Consequences

- The proxy is the single point responsible for prefix stripping — app containers need no
  knowledge of the workspace or app ID in their URL configuration
- New app types work without proxy changes as long as they serve from `/`
- Apps that cannot serve from `/` (e.g. tools with hardcoded absolute paths) are incompatible
  with this architecture and would require a dedicated ingress or URL rewriting at the response level
