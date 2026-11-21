---
name: obi-sandbox-sizing
description: Choosing the OBI (Open Brain Institute) sandbox size with the `profile` argument of execute-python / execute-shell, switching sizes, and handling a sandbox that is still starting. Use before memory- or CPU-heavy work in the OBI sandbox, when a call fails because a different size is already running, when a call returns status "starting", or when work in the sandbox dies from running out of memory.
license: Apache-2.0
---

# OBI sandbox sizing

## Sizes

`execute-python` and `execute-shell` take an optional `profile`:

| `profile` | CPU | RAM | Cost |
| --- | --- | --- | --- |
| *(omitted)* | 1–2 | 2 GB | 1x |
| `small` | 1 | 2 GB | 1x |
| `medium` | 2 | 4 GB | 2x |
| `large` | 2 | 8 GB | 3x |
| `fullnode` | 4 | 16 GB, dedicated machine | 4x |

Cost is relative credits per unit of time, charged to the project the sandbox runs in.

- Omit `profile` unless the work needs more. Omitting it uses whichever sandbox is already running.
- Pick the smallest size that fits. Ask the user before `fullnode`.
- Signs a bigger size is needed: `MemoryError`, `Killed`, a kernel that dies or restarts mid-run, or loading a circuit or dataset close to the current RAM.
- Each project has its own sandbox, so the size applies to that project only.

## Switching size

A running sandbox keeps its size. Asking for a different `profile` fails before any code runs, and the error names the running size.

To switch:
1. Ask the user. Killing the sandbox loses the running kernel (variables, imports) and `/tmp`. The home directory (`~`) is kept.
2. Save anything needed to `~` first.
3. Call `kill-sandbox`, then retry with the new `profile`.

To keep the running sandbox instead, retry without `profile`.

## A sandbox that is still starting

A call can return `status: "starting"`: nothing ran yet. The result includes `startup` with:
- `phase`: where the start has got to;
- `waited_seconds`: how long it has been starting;
- `new_machine`: whether a new machine is being added;
- `retry_after_seconds`: how long to wait before calling again.

- Wait about `retry_after_seconds`, then call the same tool again with the same arguments. The start continues between calls.
- Do not call `kill-sandbox`; it throws the progress away.
- `new_machine: true` (typical for a first `fullnode` start) can take a few minutes in total. Tell the user it is starting.

## Checking the actual limits

From inside the sandbox:

```bash
cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max
```

- `memory.max`: bytes, or `max` on a dedicated machine.
- `cpu.max`: `<quota> <period>`, e.g. `200000 100000` = 2 CPUs.

`nproc`, `free` and `os.cpu_count()` report the whole machine, not the sandbox's limit.
