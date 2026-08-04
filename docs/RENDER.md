# Deploying to Render (authenticated HTTP)

This server runs over stdio by default. Setting `FASTMCP_TRANSPORT=http` switches it to a
listening HTTP service so remote clients — including phones — can reach it.

An HTTP endpoint is reachable by anyone who learns the URL, and every tool call returns
personal health data, so `MCP_AUTH_TOKEN` is mandatory: the server exits rather than
starting an unauthenticated HTTP listener.

## What you need

| Secret | Where it comes from | What it protects |
| --- | --- | --- |
| `MCP_AUTH_TOKEN` | You generate it: `openssl rand -hex 32` | Who may call the server |
| `GARMIN_TOKEN_DATA` | Contents of `~/.garminconnect_base64` after running `garmin-connect-mcp auth` locally | Access to your Garmin account |

`GARMIN_TOKEN_DATA` is used instead of your email and password: the deployed server never
needs the account password, and cannot be prompted for an MFA code.

Neither value belongs in the repository. Both are declared `sync: false` in `render.yaml`,
so Render asks for them in the dashboard and stores them as secrets.

## Step 1 — Authenticate locally first

Tokens must be generated on a machine where you can answer an MFA prompt:

```bash
garmin-connect-mcp auth
```

Copy the token blob to your clipboard:

```bash
cat ~/.garminconnect_base64 | pbcopy    # macOS
```

## Step 2 — Push to a repository you own

Render deploys from a Git repository you control, so fork the project (or push this
checkout to your own remote) and commit the deployment files.

## Step 3 — Create the service on Render

Using the blueprint (recommended, since `render.yaml` pins the settings):

1. Render dashboard → **New** → **Blueprint**
2. Select your repository. Render reads `render.yaml` and proposes a Docker web service.
3. Render prompts for the two `sync: false` secrets. Paste them.
4. Apply, and wait for the first Docker build.

Configuring manually instead: **New** → **Web Service**, runtime **Docker**, Dockerfile
path `./Dockerfile.render`, health check path `/health`, then add the environment
variables from the table above plus `FASTMCP_TRANSPORT=http`.

Do not set `PORT`. Render assigns it, and the server reads it automatically.

## Step 4 — Verify

`/health` is unauthenticated by design, so Render's probe does not consume your Garmin
rate limit:

```bash
curl https://YOUR-SERVICE.onrender.com/health          # -> ok
```

The MCP endpoint must reject unauthenticated callers:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://YOUR-SERVICE.onrender.com/mcp                # -> 401
```

## Optional — connecting from Claude's "Connect" UI (OAuth bridge)

Claude Desktop and claude.ai only support two ways to authenticate a custom connector:
a real OAuth flow (Client ID, optional Client Secret), or an admin-only "request
headers" beta that isn't available on every account. There's no field to paste a raw
bearer token, so `MCP_AUTH_TOKEN` alone — while it's all `curl` or a manual MCP client
needs — isn't enough for Claude's UI on its own.

Setting `OAUTH_CLIENT_SECRET` turns on a minimal, single-client OAuth server
(`SingleClientOAuthBridge`) that lets Claude complete its normal "Connect" flow while
`MCP_AUTH_TOKEN` remains the actual credential underneath: the token Claude receives at
the end of the OAuth exchange **is** `MCP_AUTH_TOKEN`, verified by the exact same
`StaticTokenVerifier` used for direct/manual clients. Dynamic client registration is
disabled — the only client that can ever complete the flow is the one you configure by
hand in Claude, using the values below.

### Add two more environment variables

In the Render dashboard, service → **Environment** (this is a manual step — these
variables are not in `render.yaml`, since the OAuth bridge is optional and shouldn't be
forced on everyone who deploys the blueprint):

| Variable | Value | Notes |
| --- | --- | --- |
| `OAUTH_CLIENT_SECRET` | `openssl rand -hex 32` | A second secret, separate from `MCP_AUTH_TOKEN`. Whoever has this can request tokens from the OAuth endpoints, so treat it the same as `MCP_AUTH_TOKEN`: nobody but you. |
| `OAUTH_CLIENT_ID` | any short string, e.g. `garmin-connect-mcp` | Not secret — it's the public "username" side of the OAuth client. Optional: defaults to `garmin-connect-mcp` if unset. |

You do **not** need to set `MCP_PUBLIC_URL` on Render — it falls back to
`RENDER_EXTERNAL_URL`, which Render sets automatically for every web service.

### Add the connector in Claude

1. Claude → **Settings** → **Connectors** → **Add custom connector**
2. URL: `https://YOUR-SERVICE.onrender.com/mcp`
3. Authentication: **OAuth**
   - Client ID: the `OAUTH_CLIENT_ID` value above
   - Client Secret: the `OAUTH_CLIENT_SECRET` value above
4. Connect. Claude redirects through `/authorize` and back with no login prompt (by
   design — see the module docstring in `oauth_bridge.py` for why that's safe here) and
   should show as connected immediately.

### Verify the OAuth endpoints directly (optional)

```bash
# Dynamic client registration must be OFF (404 confirms it):
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://YOUR-SERVICE.onrender.com/register
# -> 404

# Discovery metadata should list /authorize and /token but no registration_endpoint:
curl -s https://YOUR-SERVICE.onrender.com/.well-known/oauth-authorization-server
```

If Claude reports a connection error, double-check the Client ID/Secret were pasted
without extra whitespace, and that the service has finished redeploying after you added
the two variables (Render restarts the service on env var changes).

## Operational caveats

These are properties of Garmin's unofficial API and of hosting, not of the deployment
configuration:

- **Datacenter IPs may be blocked.** Garmin fronts its login endpoints with Cloudflare
  and is known to challenge cloud provider addresses. Authentication that works from
  home may fail from Render.
- **Tokens expire and cannot be rewritten.** The access token lasts roughly 24 hours and
  is refreshed in memory using the refresh token. Because the container filesystem is
  ephemeral and environment variables are read-only, a refreshed token is not persisted.
  When the refresh token itself stops working, re-run step 1 and update
  `GARMIN_TOKEN_DATA`.
- **Every tool call performs a fresh login.** `ConfigMiddleware` builds a new client per
  call, and each login also fetches your profile and settings. One tool call therefore
  costs several Garmin API requests, which makes HTTP 429 rate limiting more likely than
  with occasional desktop use.
- **Free instances sleep.** A cold start can take long enough for an MCP client to time
  out; the first request after idling may need a retry.
