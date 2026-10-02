---
name: obi-sandbox-auth
description: Manages authentication against the OBI (Open Brain Institute) auth-manager API from inside the OBI sandbox. Covers three triggers — (1) exchanging the sandbox's built-in OBI_ACCESS_TOKEN once at session start for a persistent token id, (2) minting a fresh access token from that id whenever a credential is needed (no bearer required, no expiry bookkeeping), and (3) obtaining offline-access consent before launching a Neurodamus/CoreNeuron circuit simulation of more than 20 neurons (the point at which obi-one routes the job to cluster resources; Brian2 and inait never need it). Use this skill whenever a task touches the OBI sandbox (execute-python, execute-shell), OBI's auth-manager endpoints, or a simulation launch — do not call these endpoints ad hoc without consulting it first, since ordering and header format matter. OBI_ACCESS_TOKEN expires in minutes, so never treat it as a session-long credential or try to keep it alive.
license: Apache-2.0
---

# OBI Sandbox Authentication

> **Related generic skills:** [[obi-links]] — nothing from this skill is ever shown to the user, but the vlab/project ids used in the headers here are the same ones that go into a workflow link. Tokens, token ids, and consent URLs are never linked or displayed.

This skill governs how to authenticate against OBI's `auth-manager` API (base path `/api/auth-manager/v1/...` on the relevant OBI environment, e.g. `https://staging.cell-a.openbraininstitute.org`) from inside the OBI sandbox. The sandbox always exposes a short-lived bearer token as the `OBI_ACCESS_TOKEN` environment variable — never hardcode a token value, always reference `$OBI_ACCESS_TOKEN` inline in the `curl` call so the shell substitutes the current value.

## The model: exchange once, then mint on demand

**`OBI_ACCESS_TOKEN` is an ordinary Keycloak access token and it expires in minutes, not hours.** Do not treat it as a session-long credential, and do not try to keep it alive — access tokens are not designed to be extended. Only the *refresh* token can be long-lived, and auth-manager already vaults that for you.

So the whole scheme is two steps:

1. **Once, at session start:** exchange `OBI_ACCESS_TOKEN` for a vaulted refresh token, and keep the **persistent token id** you get back.
2. **Every time you need a credential after that:** mint a fresh access token from that id. `POST /v1/access-token` requires **no bearer token at all** — only the `id` header — so it works regardless of whether `OBI_ACCESS_TOKEN` has expired.

There is no expiry bookkeeping to do, and nothing to poll. If you find yourself tracking elapsed time to decide whether a token is still good, you are on the wrong path — just mint a new one.

## Trigger 1 — Session start: exchange the token

**When:** The first time the OBI sandbox is used in a session (first `execute-python`/`execute-shell` call), before anything else that needs auth. `OBI_ACCESS_TOKEN` is still fresh at this point; that window is short, so do this early.

**Action:**
```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  -H "Authorization: Bearer $OBI_ACCESS_TOKEN" \
  https://<obi-host>/api/auth-manager/v1/token-exchange
```

**Expected:** `HTTP 200` with `{"data":{"id":"<persistent-token-id>"}}`.

That `id` is **the UUID of the stored refresh token**, not a session identifier. It is the credential that matters for the rest of the session: hold onto it and feed it to `/v1/access-token` (Trigger 2) whenever you need a usable token. The endpoint exchanges your bearer token with Keycloak, stores the resulting refresh token in auth-manager's vault, and hands back this id.

**If it instead returns `{"error":"Token is not active","code":"token_not_active"}`:** the sandbox's token has already expired. Call the sandbox-kill tool (`kill-sandbox` on the OBI connector) to tear down and recreate the sandbox — this issues a fresh `OBI_ACCESS_TOKEN` automatically — then retry the exchange once.

## Trigger 2 — Any time you need a usable access token

**When:** Before any call that needs a bearer credential — an auth-manager call, a simulation launch, a downstream API request. There is no time threshold to track: mint one whenever you need one, and mint a new one rather than reusing an old one.

**Action:**
```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  -H "id: <persistent-token-id from Trigger 1>" \
  https://<obi-host>/api/auth-manager/v1/access-token
```

**Expected:** `HTTP 200` with `{"data":{"access_token":"<jwt>","expires_in":3600}}`.

Note there is **no `Authorization` header** here — this endpoint is unauthenticated by design and mints from the vaulted refresh token. That is precisely why it keeps working after `OBI_ACCESS_TOKEN` has expired, and why no keep-alive mechanism is needed.

**If this fails**, the vaulted refresh token or the underlying SSO session is gone — not a matter of elapsed time since the last call. Recover as in Trigger 1: kill and recreate the sandbox, then redo the exchange to vault a new refresh token.

### What *not* to do

- **Don't poll `refresh-token-id` on a timer as a keep-alive.** `POST /v1/refresh-token-id` requires a valid `Authorization: Bearer` header, so once `OBI_ACCESS_TOKEN` has expired — which happens in minutes — it just returns 401. A scheme that checks in every couple of hours would 401 on every attempt while appearing to be a working refresh loop. It also does not extend the SSO session's idle timer or the vaulted token's lifetime; there is no call here that buys you more time.
- **Don't infer token validity from elapsed time.** If you genuinely need to test a token rather than just mint a new one, `GET /v1/validate-token` introspects it with Keycloak and returns `{"data":{"valid":true|false}}`. Minting is almost always simpler.

## Trigger 3 — Offline-access consent before a large simulation

**When:** About to launch a **Neurodamus/CoreNeuron** circuit simulation of **more than 20 neurons**. Do this check before kicking off the simulation job, not after.

Why 20: obi-one derives a circuit's *scale* from its neuron count — `single` (1), `pair` (2), `small` (≤ 20, `MAX_SMALL_MICROCIRCUIT_SIZE`), and `microcircuit` above that. For the NEURON/CoreNeuron simulators, `single`/`pair`/`small` route to `circuit_simulation_neurodamus_machine`, which is session-scoped and needs no offline token; anything larger routes to `circuit_simulation_neurodamus_cluster`, which runs on cluster resources and does require consent. **The routing is automatic** — the caller does not pick machine vs cluster, obi-one derives it from the circuit, so the neuron count is the only thing to check.

**Scope — this applies to Neurodamus/CoreNeuron only.** Brian2 and inait (LearningEngine) simulations have no cluster variant at all, so they never need the offline flow regardless of neuron count.

> Not to be confused with the `max_neurons=100` in obi-one's cluster instance table: that picks the `small` vs `large` instance size *once a job is already on the cluster path*. It is not the machine-vs-cluster cutoff and has nothing to do with whether consent is needed.

This is a multi-step flow because it needs a human in the loop:

**Step 3a — Request the offline token / consent URL:**
```bash
curl -s -w '\nHTTP %{http_code}\n' \
  -H "Authorization: Bearer $OBI_ACCESS_TOKEN" \
  https://<obi-host>/api/auth-manager/v1/offline-token
```
Returns `HTTP 200` with a `consent_url`, `session_state_id`, and a message asking the user to visit the URL.

**Step 3b — Show the user the consent URL.** This is required — do not skip or try to complete consent on the user's behalf. Present it as an actual clickable link (not truncated, not raw with unescaped spaces — encode the `scope` param's spaces as `%20` before rendering it). Explain in one line what it's for: authorizing offline access so the simulation can keep running without the user staying logged in. **Tell the user to open the consent URL in their operating system's default browser** — the one already signed in to their OBI/SSO session — rather than an incognito window or a different browser, so the consent completes against the active session. Then wait for the user to confirm they've completed it before continuing — do not poll or guess.

**Step 3c — Confirm the offline token was persisted:**
```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  -H "Authorization: Bearer $OBI_ACCESS_TOKEN" \
  https://<obi-host>/api/auth-manager/v1/offline-token-id
```
Returns `HTTP 200` with `{"data":{"persistent_token_id":"...","session_state_id":"..."}}`. If this doesn't yet show a `persistent_token_id`, the user likely hasn't finished the consent step — ask them to confirm rather than proceeding.

**Step 3d — Mint an access token from the `persistent_token_id`:** exactly the Trigger 2 call, using the offline `persistent_token_id` from step 3c in place of the one from Trigger 1:
```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST \
  -H "id: <persistent_token_id from step 3c>" \
  https://<obi-host>/api/auth-manager/v1/access-token
```
Returns `HTTP 200` with `{"data":{"access_token":"<jwt>","expires_in":3600}}`. Use this `access_token` as the bearer credential for the simulation launch call.

The difference between the two ids is *what got vaulted*, not how you use them: Trigger 1 vaults an ordinary refresh token tied to the user's SSO session, while the consent flow vaults an **offline** token that outlives it — which is why a long-running simulation needs this path. Either way, mint fresh whenever you need a credential (step 3d again with the same `persistent_token_id`); never restart the consent flow from 3a just because a token aged out.

## Handling secrets

- Never print a full `access_token`, `OBI_ACCESS_TOKEN` value, or the `state`/`nonce` JWT embedded in the consent URL into chat or a file. If asked to log or save output from these calls, redact/scramble token and ID values first, keeping endpoint paths, HTTP status codes, and structure intact.
- It's fine to show a short prefix (e.g. first ~20 chars) of a token if the user explicitly asks for confirmation it exists, but not the full value.
- The `consent_url` itself must be shown in full and unredacted to the user (Step 3b) — it's meant for them to click — but treat it as a one-time, session-bound link and don't forward it anywhere else (e.g. don't paste it into a shared doc).
- **Nothing from this skill belongs in a session logbook** — not tokens, not consent URLs, not the endpoints or status codes, not the fact that a token was minted. Authentication is plumbing; see the "What never goes in" list in [[obi-logbook]].
- **The persistent token id is itself a credential.** Anyone holding it can mint access tokens without authenticating, since `/v1/access-token` takes no bearer. Treat it like a token: keep it in memory for the session, never print it in full, never write it to a file.

## Quick reference

| Step | Endpoint | Method | Auth header | Returns |
|---|---|---|---|---|
| 1. Token exchange (once, at session start) | `/token-exchange` | POST | `Authorization: Bearer $OBI_ACCESS_TOKEN` | `data.id` — the persistent token id |
| 2. Mint an access token (every time one is needed) | `/access-token` | POST | `id: <persistent token id>` — **no bearer** | `data.access_token`, `data.expires_in` |
| 3a. Offline consent URL | `/offline-token` | GET | `Authorization: Bearer $OBI_ACCESS_TOKEN` | `data.consent_url`, `data.session_state_id` |
| 3c. Offline token id | `/offline-token-id` | POST | `Authorization: Bearer $OBI_ACCESS_TOKEN` | `data.persistent_token_id` |
| 3d. Mint from the offline id | `/access-token` | POST | `id: <persistent_token_id>` — **no bearer** | `data.access_token`, `data.expires_in` |

`/v1/refresh-token-id` and `/v1/refresh-token` also exist and return a new persistent token id, but both require a valid `Authorization: Bearer` header — so neither is usable once `OBI_ACCESS_TOKEN` has expired, and neither is a keep-alive. `GET /v1/validate-token` introspects a token with Keycloak and returns `data.valid`.
