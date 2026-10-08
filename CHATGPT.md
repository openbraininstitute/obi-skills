# Using obi-skills with ChatGPT and Codex

This guide explains how to install the OBI Agent Skills from this repository and
connect to the OBI platform through the **`neuroagent`** MCP server.

Choose the instructions for your client:

- **Codex:** reads local skill directories and can receive an OAuth callback on
  your computer.
- **Hosted ChatGPT:** requires support for custom connectors / MCP servers. Load
  skill instructions into a conversation or Project, and use the callback URL
  supplied by ChatGPT's connector setup.

## 1. Install the skills

The skills follow the [Agent Skills](https://agentskills.io/) format and live
under [`skills/`](./skills/). Each skill is a directory containing a `SKILL.md`.

### Codex

Clone the branch containing the NGV metabolism skill:

```bash
git clone --branch add-ngv-metabolism-skill \
  https://github.com/openbraininstitute/obi-skills.git
cd obi-skills
```

If you already have a checkout, use that checkout on the
`add-ngv-metabolism-skill` branch. The unqualified clone command selects the
default branch, which may not contain the same skills.

From the repository root, link all skills into your Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
for skill in "$PWD"/skills/*; do
  [ -f "$skill/SKILL.md" ] || continue
  target="${CODEX_HOME:-$HOME/.codex}/skills/$(basename "$skill")"
  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "Already installed; review before updating: $target"
  else
    ln -s "$skill" "$target"
  fi
done
```

Existing installations are left intact. Review any skipped skills if you need
the version from this branch. Keep the repository at this location while using
the symlinks. The installed skills are available on your next Codex turn.

### Hosted ChatGPT

ChatGPT does not read your local Codex skills directory. Make a skill available by:

- pasting its `SKILL.md` into the conversation; or
- adding it and any referenced supporting files to a ChatGPT Project.

For example, load
[`skills/ngv-metabolism/SKILL.md`](./skills/ngv-metabolism/SKILL.md).
The MCP connector below supplies the tools that the instructions refer to.

## 2. Connect the `neuroagent` MCP server

Use the production endpoint:

```text
https://cell-a.openbraininstitute.org/api/agent-ts/mcp
```

The connection uses streamable HTTP and OAuth with client ID `obi-mcp` and scopes
`openid profile email`. Use staging only when deliberately testing against it.

### Codex configuration

Add the following to `~/.codex/config.toml` (or `$CODEX_HOME/config.toml` if
configured). If `neuroagent` already exists, update its tables instead of adding
duplicate tables. Back up the file before changing an existing connection.

```toml
[mcp_servers.neuroagent]
url = "https://cell-a.openbraininstitute.org/api/agent-ts/mcp"
scopes = ["openid", "profile", "email"]

[mcp_servers.neuroagent.oauth]
client_id = "obi-mcp"
callback_port = 8080
callback_url = "http://localhost:8080/callback"
```

Use `localhost` explicitly. Setting `callback_port` alone can leave Codex using
`127.0.0.1`, which was rejected by the production AWS front end during testing.

These fields are documented in the
[Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
The callback port must be free on the computer running Codex.

### Keycloak configuration for Codex

In the production Keycloak realm **SBO**, open the **obi-mcp** client and add the
callback under **Valid redirect URIs**. For the base configuration above, use:

```text
http://localhost:8080/callback
```

Codex can generate an additional server-specific suffix, resulting in:

```text
http://localhost:8080/callback/<generated-id>
```

Check the actual `redirect_uri` in the authorization URL printed by Codex. Decode
it before entering it into Keycloak (`%3A` is `:`, and `%2F` is `/`). Register the
complete URL, including its port and path, and click **Save**.

If Codex generates a suffixed callback with `127.0.0.1`, stop that login attempt,
copy its decoded callback into `callback_url`, change only the hostname to
`localhost`, and register that complete URL in Keycloak before retrying. Preserve
the generated suffix; do not copy an ID from another installation or enter the
literal placeholder `<generated-id>`.

For deployments that intentionally support multiple callback suffixes, Keycloak
also accepts the narrower path wildcard `http://localhost:8080/callback/*`.
Prefer the exact callback URL when possible. A trailing slash alone does not
match an additional suffix. See the
[Keycloak redirect URI documentation](https://www.keycloak.org/docs/latest/server_admin/#_oidc_clients).

**Validation note:** On September 24, 2026, authentication succeeded with a full
`localhost` callback containing Codex's generated suffix. The unsuffixed template
above follows Codex's documented support for servers advertising issuer
identification, which OBI advertised during testing; that shorter variant was not
separately tested in this setup.

### Sign in from Codex

Run:

```bash
codex mcp login neuroagent
```

Complete OBI sign-in in the browser tab opened by this command. Successful
authorization prints:

```text
Successfully logged in to MCP server 'neuroagent'.
```

If `codex` is not on your shell's PATH, use the Codex desktop MCP sign-in controls
or the CLI bundled with your installation. On the macOS installation used for
testing, the command was:

```bash
/Applications/ChatGPT.app/Contents/Resources/codex mcp login neuroagent
```

That application path is installation-specific.

### Hosted ChatGPT connector

In ChatGPT's custom connector / MCP settings, configure:

| Field | Value |
| --- | --- |
| Name | `neuroagent` |
| Transport | Streamable HTTP / remote MCP |
| URL | `https://cell-a.openbraininstitute.org/api/agent-ts/mcp` |
| Authentication | OAuth |
| OAuth client ID, if requested | `obi-mcp` |
| OAuth scopes, if configurable | `openid profile email` |

Use the exact callback URL supplied by ChatGPT's connector setup and register it
in Keycloak as required. The local Codex callback and port `8080` do not configure
hosted ChatGPT's OAuth redirect. Complete the connector's OBI sign-in flow and
enable it for the intended conversation or Project.

## 3. Verify the setup

1. Confirm that the MCP connection is authorized. In Codex, successful
   `codex mcp login neuroagent` output confirms OAuth authorization;
   `codex mcp get neuroagent` shows the configured endpoint.
2. Confirm that the conversation exposes the server's tools, including
   `execute-python`, and has access to the desired skill. Authorization alone
   does not verify tool availability or a simulation run.
3. For an optional NGV metabolism smoke test, ask:

   > Run the NGV unit metabolism model for the `young` phenotype with `mainSyn`
   > stimulation and plot neuronal ATP.

   The agent should call `execute-python`, run `run_metabolism`, and return a plot.

## Troubleshooting

- **403 before the OBI login screen:** During testing on September 24, 2026,
  authorization requests containing a `127.0.0.1` callback returned an AWS
  `403 Forbidden`, while `localhost` requests reached the login page. Configure
  `localhost` in Codex and register its matching callback in Keycloak. This was
  an upstream rejection, not evidence of an expired OAuth token; the specific
  AWS filtering rule was not identified.
- **Invalid redirect URI:** Check the production **SBO** realm's **obi-mcp**
  client. Compare the complete decoded `redirect_uri` with the saved entry,
  including hostname, port, path, and any generated suffix. Save the changes.
- **Address already in use:** Close your previous authentication attempt before
  retrying. If another application occupies port `8080`, resolve the conflict
  before starting a new login.
- **Authentication timed out:** Start a fresh login and use the newest browser
  tab. Old authorization URLs belong to earlier login attempts.
- **401/403 when calling MCP tools after login:** Check token validity and
  account/project permissions. Reauthorize if credentials expired. A 403 can
  also indicate insufficient access rather than an authentication failure.
- **No connector option in ChatGPT:** Your client or plan must support custom
  MCP connectors.
- **Tools not offered in a conversation:** Enable the connector for that
  conversation or Project; in Codex, reload the MCP connection or start a new
  task if needed. Ensure the skill instructions are also available.
- **Wrong host:** Verify that the MCP URL uses
  `https://cell-a.openbraininstitute.org/api/agent-ts/mcp` and not staging unless
  staging was explicitly intended.
