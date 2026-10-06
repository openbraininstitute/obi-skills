# obi-skills

Agent Skills for the Open Brain Institute (OBI) platform — reusable instructions that teach AI agents how to authenticate, link results, keep scientific logbooks, and drive OBI APIs (data integration, circuit simulation, single-cell / ion-channel modeling, skeletonization, visualization, and related workflows).

Skills follow the [Agent Skills](https://agentskills.io/) format and live under [`skills/`](./skills/). Install or symlink them into your agent’s skills directory (e.g. `.cursor/skills/`, `.claude/skills/`, `.kiro/skills/`), or point your tool at this folder.

| Skill | Purpose |
| --- | --- |
| [`chat-obi-sandbox-bridge`](./skills/chat-obi-sandbox-bridge/SKILL.md) | Claude Chat ↔ OBI sandbox file bridge |
| [`data-integration-api`](./skills/data-integration-api/SKILL.md) | Ingest morphologies, circuits, and metadata via obi-one |
| [`disease-modeling`](./skills/disease-modeling/SKILL.md) | End-to-end disease / condition modeling on a microcircuit |
| [`ion-channel-api`](./skills/ion-channel-api/SKILL.md) | Fit and simulate ion channel models |
| [`morphoviewer-standalone`](./skills/morphoviewer-standalone/SKILL.md) | Standalone HTML morphology / circuit viewers |
| [`obi-circuit-simulation`](./skills/obi-circuit-simulation/SKILL.md) | SONATA circuit download, modify, register, and simulate |
| [`obi-links`](./skills/obi-links/SKILL.md) | Hyperlink entities, sandbox paths, and launched jobs |
| [`obi-logbook`](./skills/obi-logbook/SKILL.md) | Scientific logbook convention for OBI workflows |
| [`obi-sandbox-auth`](./skills/obi-sandbox-auth/SKILL.md) | Auth-manager token exchange and offline consent |
| [`single-cell-simulation-api`](./skills/single-cell-simulation-api/SKILL.md) | ME-model building and single-neuron simulation |
| [`skeletonization-api`](./skills/skeletonization-api/SKILL.md) | Skeletonization campaigns via obi-one / EntityCore |
| [`virtual-lab-manager-api`](./skills/virtual-lab-manager-api/SKILL.md) | Virtual labs, projects, and credits |

Example install with the skills CLI (if you use it):

```bash
npx skills add openbraininstitute/obi-skills
```

# Claude plugin

This repository is also a Claude plugin (`obi-skills`) that bundles all skills above with the production `neuroagent` MCP server (`https://cell-a.openbraininstitute.org/api/agent-ts/mcp`, OAuth public client `obi-mcp`, no client secret, scopes `openid profile email`).

Install in Claude Code:

```
/plugin marketplace add openbraininstitute/obi-skills
/plugin install obi-skills@obi-skills
```

Sign-in uses the local callback `http://localhost:8080/callback`, which must be registered in the `obi-mcp` client of the production Keycloak realm `SBO`. Port 8080 must be free while signing in.

**Releasing changes:** whenever a skill or the MCP config changes, bump `version` in [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json) in the same PR. Installed plugins are cached by version, so without a bump existing users will not receive the update. Keep the plugin name `obi-skills` so an update replaces the old version instead of adding a second plugin.

# Licence

Licensed under the Apache License, Version 2.0. See [LICENSE](./LICENSE).

# Acknowledgements

Copyright © 2025-2026 Open Brain Institute
