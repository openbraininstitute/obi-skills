# Using obi-skills with Claude

This guide installs the OBI Agent Skills from this repository **and** the
**`neuroagent`** MCP server into Claude as a single plugin, `obi-skills`.

**How to use it:** give Claude this file (paste it, attach it, or link it) and
say *"Follow these instructions."* Everything below the line addressed to
Claude is written as instructions for Claude to carry out. The Keycloak step
(section 4) is for an OBI administrator and must be done once per callback URL.

It works in Claude (web, desktop, Cowork) and Claude Code. Both can build and
install a `.plugin` file.

---

## Instructions for Claude

Build a plugin named `obi-skills` containing every skill under `skills/` on the
`add-ngv-metabolism-skill` branch plus the `neuroagent` MCP server, validate it,
and deliver it to the user as `obi-skills.plugin`. Do not change any skill's
content or name. Use only the values given here: do not add a client secret,
different scopes, or a staging endpoint unless the user asks for them.

### 1. Get the skills

Clone the branch into your working/scratch directory (the default branch may
not contain the same skills, so always name the branch):

```bash
git clone --depth 1 --branch add-ngv-metabolism-skill \
  https://github.com/openbraininstitute/obi-skills.git
cd obi-skills
git log -1 --format='%h %s (%ci)'   # report this commit to the user at the end
```

List the skills (each is a directory under `skills/` containing a `SKILL.md`)
and check that each `SKILL.md` has YAML frontmatter with `name` matching its
directory name and a `description`. If one does not, stop and tell the user
which one, rather than editing it.

### 2. Assemble the plugin

```bash
PLUGIN=../obi-skills-plugin
rm -rf "$PLUGIN" && mkdir -p "$PLUGIN/.claude-plugin"
cp -r skills "$PLUGIN/"
cp README.md LICENSE "$PLUGIN/"
```

Write `$PLUGIN/.claude-plugin/plugin.json`:

```json
{
  "name": "obi-skills",
  "version": "0.3.0",
  "description": "Agent Skills for the Open Brain Institute platform (auth, links, logbook, circuit / single-cell / ion-channel simulation, data integration, skeletonization, virtual labs, NGV metabolism) plus the neuroagent MCP server.",
  "author": { "name": "Open Brain Institute" },
  "repository": "https://github.com/openbraininstitute/obi-skills/tree/add-ngv-metabolism-skill",
  "license": "Apache-2.0"
}
```

Write `$PLUGIN/.mcp.json` at the plugin root (not inside `.claude-plugin/`):

```json
{
  "mcpServers": {
    "neuroagent": {
      "type": "http",
      "url": "https://cell-a.openbraininstitute.org/api/agent-ts/mcp",
      "oauth": {
        "clientId": "obi-mcp",
        "callbackPort": 8080
      }
    }
  }
}
```

About this configuration:

- **Transport:** streamable HTTP (`"type": "http"`).
- **OAuth client:** OBI's own public client `obi-mcp`. It has **no client
  secret**, so do not add `clientSecret`, do not prompt for one and do not set
  `MCP_CLIENT_SECRET`. The OAuth flow uses PKCE.
- **Scopes:** `openid profile email`. OBI advertises these in its OAuth
  metadata, so no scope field is needed in the config.
- **Callback:** Claude Code listens on `http://localhost:8080/callback`. That
  exact URL must be registered in Keycloak (section 4). Keep `localhost`: during
  testing, the production AWS front end rejected callbacks on `127.0.0.1` with a
  `403`.
- **Endpoint:** production by default. Use staging only if the user explicitly
  asks for it (see *Staging environment* below).

#### Staging environment

If the user asks for the staging environment, use this URL instead:

```text
https://staging.cell-a.openbraininstitute.org/api/agent-ts/mcp
```

Keep everything else the same: `"type": "http"`, client ID `obi-mcp`, no secret,
and `callbackPort` 8080. If the user wants **both** environments, add staging as
a second server named `neuroagent-staging` alongside `neuroagent`. Keep the
production server named `neuroagent`. The callbacks must also be registered in
the `obi-mcp` client of the **staging** Keycloak, which is separate from
production (see section 4). Report in your final message which environment(s)
the plugin points at.

If `claude` is available on the command line, you can generate the same entry
instead of writing it by hand and compare the two:

```bash
claude mcp add --transport http --scope project \
  --client-id obi-mcp --callback-port 8080 \
  neuroagent https://cell-a.openbraininstitute.org/api/agent-ts/mcp
# writes .mcp.json in the current directory. Do not pass --client-secret.
```

Append this section to `$PLUGIN/README.md` so the plugin documents itself:

```markdown
## MCP server (neuroagent)

Bundled server: `https://cell-a.openbraininstitute.org/api/agent-ts/mcp`
(streamable HTTP, OAuth public client `obi-mcp`, no secret, scopes
`openid profile email`). Local callback: `http://localhost:8080/callback`,
which must be registered in the `obi-mcp` client of the production Keycloak
realm `SBO`. Port 8080 must be free while signing in.
```

### 3. Validate and package

Validate with `claude plugin validate "$PLUGIN/.claude-plugin/plugin.json"`. If
the CLI is not available, check the following by hand and report it the way the
validator would:

- `.claude-plugin/plugin.json` is valid JSON and its `name` is kebab-case.
- `.mcp.json` is valid JSON with exactly one server, `neuroagent`, whose
  `oauth` block contains `clientId: "obi-mcp"` and no secret.
- Every directory under `skills/` contains a `SKILL.md`, and the count matches
  the repository.

Package the plugin and deliver it:

```bash
cd "$PLUGIN" && zip -qr ../obi-skills.plugin . -x "*.DS_Store"
```

Send `obi-skills.plugin` to the user as a file. In Claude it appears as a card
with an install button. In Claude Code, install it with the plugin commands
instead.

### 4. Register the callback in Keycloak (OBI admin, once)

Tell the user that this step is needed, and that you cannot do it for them.

In the production Keycloak realm **SBO**, open the **obi-mcp** client, add the
callback URL(s) below under **Valid redirect URIs**, and click **Save**:

| Where Claude runs the MCP server | Redirect URI to register |
| --- | --- |
| Claude Code, or the plugin running on the user's computer | `http://localhost:8080/callback` |
| Claude on the web, or cloud sessions (added as a claude.ai connector) | `https://claude.ai/api/mcp/auth_callback` |

When sign-in fails with *Invalid redirect URI*, read the `redirect_uri`
parameter in the authorization URL, decode it (`%3A` is `:`, `%2F` is `/`), and
register that exact value, including host, port and path.

For the staging server, register the same redirect URIs in the `obi-mcp`
client of the **staging** Keycloak realm. Production and staging keep separate
lists.

**Alternative for claude.ai without the plugin:** in Settings → Connectors →
Add custom connector, enter the server URL above. Under **Advanced settings**,
set **OAuth Client ID** to `obi-mcp` and leave the client secret empty. This
uses the `https://claude.ai/api/mcp/auth_callback` redirect.

### 5. Tell the user what to clean up

Before finishing, check whether the user already has standalone (non-plugin)
copies of any of these skills, or another OBI connector pointing at the same
server. If so, name them and tell the user to remove the duplicates in Settings
after installing the plugin. Otherwise the skills and tools appear twice. Keep
standalone skills that are not in this repository (e.g.
`multiscale-disease-demo`).

### 6. Verify (after the user installs the plugin)

1. **Sign in.** Connect `neuroagent` and complete the OBI sign-in in the browser
   window that opens. Use the default browser that is already signed in to OBI.
   Port `8080` must be free.
2. **Check the tools.** In a new conversation, confirm that the `neuroagent`
   tools are present, including `execute-python` and
   `get-default-virtual-lab-and-project`. Authorization alone does not prove
   that the tools are available.
3. **Optional smoke test.** Ask:

   > Run the NGV unit metabolism model for the `young` phenotype with `mainSyn`
   > stimulation and plot neuronal ATP.

   Claude should load the `ngv-metabolism` skill, call `execute-python`, run
   `run_metabolism`, and return a plot plus a JupyterLab link.

### Troubleshooting

- **403 before the OBI login page:** the callback used `127.0.0.1`. Use
  `localhost`.
- **Invalid redirect URI:** the exact callback is not registered in
  SBO → obi-mcp (see section 4).
- **Address already in use:** an earlier sign-in or another app is holding
  port 8080. Close it and retry.
- **Authentication timed out:** start a new sign-in and use the newest browser
  tab. Old authorization URLs belong to earlier attempts.
- **Asked for a client secret:** there is none. Remove any `clientSecret` or
  `MCP_CLIENT_SECRET` and retry.
- **401/403 on tool calls after login:** the token has expired or the account
  lacks project access. Sign in again, and see the `virtual-lab-manager-api`
  skill.
- **Wrong environment:** production is
  `https://cell-a.openbraininstitute.org/api/agent-ts/mcp`, and staging is
  `https://staging.cell-a.openbraininstitute.org/api/agent-ts/mcp`. Check which
  one the server entry uses.
- **Tools missing in a conversation:** enable the plugin or connector for that
  conversation or project, or start a new one.
