# Install the Open Brain Institute plugin (Claude Desktop / Cowork)

Instructions for Claude to install the `open-brain-institute` plugin from
<https://github.com/openbraininstitute/obi-skills> into Claude Desktop / Cowork.

The plugin bundles all OBI skills plus the production OBI MCP server, registered as
`obi` (`https://cell-a.openbraininstitute.org/api/agent-ts/mcp`). The server may also
appear as `neuroagent` — it is the same server. The repository doubles as a plugin
marketplace named `obi`.

## Steps

1. Open **Customize** in the sidebar and select **Plugins**.
2. Select **Add marketplace** and enter:
   ```
   openbraininstitute/obi-skills
   ```
3. Find **Open Brain Institute** in the list and click **Install**.
4. Open the installed plugin and go to its **Connectors** tab.
5. Before connecting `obi`, open its advanced / OAuth settings and set:
   - **OAuth Client ID:** `obi-mcp`
   - Leave the client secret empty.
6. Click **Connect** on `obi`. Installing does not sign the user in — sign-in opens in
   the browser, and the user must complete it themselves (do not enter credentials).

## Verify

- The skills appear as `open-brain-institute:<skill>` (e.g. `open-brain-institute:obi-logbook`).
- The `obi` connector shows as connected and its tools (e.g. `execute-python`,
  `list-virtual-labs-and-projects`) are available.

## Updating

Third-party marketplaces do not auto-update by default. On the `obi` marketplace,
select **Check for updates**, or turn on **Sync automatically**.
