---
name: obi-sandbox
description: How to run code in the OBI (Open Brain Institute) sandbox — which sandbox (pod) and kernel (Python process) a call runs in, running work in parallel, the ~30 s tool-call timeout and background jobs, and what to do with busy, stuck or unneeded kernels and sandboxes. Covers execute-python, execute-shell, list-sandboxes, list-kernels, interrupt-kernel, kill-kernel and kill-sandbox. Use before any long, parallel or multi-step sandbox work, when a call times out or reports a busy kernel, and before killing anything.
license: Apache-2.0
---

# The OBI sandbox

> **Related skills:** [[virtual-lab-manager-api]] — which project a call runs in and is charged to, and what is shared across projects. [[obi-sandbox-auth]] — tokens inside the sandbox. [[obi-logbook]] — where work and outputs belong (`/home/jovyan/<topic>`).

## Sandboxes and kernels

Inside one project, code runs at an address of up to three parts, all optional:

| Argument | Selects | Default |
|---|---|---|
| `vlab_id` + `project_id` | the project (see [[virtual-lab-manager-api]]) | the default workspace |
| `sandbox_number` (0–31) | a sandbox: a separate pod (machine) of that project | the project's default sandbox |
| `kernel` (`execute-python` / `execute-shell` only) | a kernel: a separate Python process inside that sandbox | `"default"` |

A **sandbox** is a pod. Different `sandbox_number`s are different machines: own CPU and memory, own `/tmp`, own kernels, own size (`profile`), stopped independently. `~` is still shared, as across projects. Each one is billed while it runs, and at most **3 run at once per user and project, the default sandbox included**; a 4th fails with "Sandbox limit reached". Call `list-sandboxes` before picking a new number, and kill numbered sandboxes you no longer need.

A **kernel** is one Python process inside a sandbox. Its variables, imports and loaded data persist between calls with the same `kernel` name, and different names never see each other's variables. Kernels in one sandbox share its CPU, memory and files; a new one starts in a second or two and costs nothing extra beyond the memory it uses. A shell command (`execute-shell`) runs through the kernel too, but each one in a fresh subshell — `cd`/`export` don't carry over to the next call, files and Python state do.

Which to use:

- **Normal, sequential work:** omit both. Everything runs in the default kernel of the default sandbox, and state persists as you'd expect.
- **Parallel work that keeps its own state** (e.g. one kernel per sub-agent, or a long job while you keep working): give each strand its own `kernel` name in the same sandbox. Cheap and fast.
- **Work that must not compete for memory/CPU, needs a different size, or must survive another strand being killed:** use a separate `sandbox_number`. Costs a cold start and a billed pod.

A kernel runs one call at a time:

- If the `"default"` kernel is busy (e.g. still running a call that timed out), a new call **runs in a temporary kernel** instead and the result says so in `note`. That call does **not** see the default kernel's variables; the temporary kernel is deleted afterwards. Nothing is interrupted.
- If a **named** kernel is busy, the call fails with "Kernel … is still running an earlier call". Wait, use another name, or stop it with `interrupt-kernel`.
- The `kernel` field of every result says where the code actually ran (`"temporary"` for the case above).

Managing kernels:

- `list-kernels` shows the kernels of a running sandbox with their state (`busy`/`idle`) and owner: `mcp` (created by these sandbox tools, yours to use — `kernel` is the name to pass to the other tools), `research-agent` (workers of a research run), or `other` (e.g. a notebook the user opened). It never starts a sandbox.
- `interrupt-kernel` stops the code currently running in one of your kernels (like Ctrl+C); its variables are kept.
- `kill-kernel` deletes one of your kernels and frees its memory; its variables are lost, files are kept, and the next call with that name starts fresh. Delete kernels you no longer need — idle ones still hold their memory until the sandbox stops.
- Only your own (`mcp`) kernels can be interrupted or killed.

**Killing a sandbox is the last resort.** `kill-sandbox` stops the pod with *every* kernel in it, including work from other conversations or clients, parallel sub-agents, or a research run sharing it. Prefer `interrupt-kernel` or `kill-kernel`; kill a sandbox only when it is broken, its token expired (see [[obi-sandbox-auth]]), or its size has to change. It refuses while the sandbox has busy or research-agent kernels — interrupt your own first, and pass `force: true` only after checking with the user. It never starts a sandbox that isn't running.

For `get-sandbox-download-url` / `get-sandbox-upload-url`, pass the same `sandbox_number` as the call that wrote the file when the path is outside `~` (e.g. `/tmp`), just as for the project ids.

## Long-running work: the ~30 s tool-call timeout

`execute-python` and `execute-shell` **return after about 30 seconds**. This is a limit on the *tool call*, not on the sandbox: when a call hits it, it comes back looking like a failure while the code often keeps running in the kernel — so you're left not knowing whether it finished, and a naive retry starts the work a second time.

**Whenever a piece of work might run longer than ~30 s — any heavy or open-ended code, not just a specific workflow — don't run it in the foreground. Start it as a background process that writes to a file, then poll for completion in later short calls.** This covers loading or processing large circuits/datasets, long `obi_one` tasks that run locally in the sandbox (e.g. connectivity-matrix extraction, batch e-feature extraction), big downloads, installs, or any arbitrary script whose runtime you can't bound up front.

The pattern:

1. **Write the code to a file, then launch it detached in one short call:**

   ```bash
   # execute-shell — returns immediately
   cd /home/jovyan/<topic>
   nohup python code/run.py > results/<run>/run.log 2>&1 &
   echo "started pid $!"
   ```

   Have the script print a clear sentinel (e.g. `echo DONE` / a final `print("DONE")`) and write its real outputs under the topic directory, so completion is unambiguous.

2. **Poll in later short calls** — check the log or the output file; never re-run the job to "see if it's done":

   ```bash
   # execute-shell — each call returns well under 30 s
   tail -n 5 /home/jovyan/<topic>/results/<run>/run.log
   ls -la /home/jovyan/<topic>/results/<run>/<expected-output> 2>/dev/null && echo COMPLETE
   ```

Things to keep in mind:

- **The kernel and filesystem persist between calls**, so a backgrounded job survives the tool call that started it. `/home/jovyan` is the durable place to write (shared per user); `/tmp` is per-pod and can vanish on a cold start.
- **A timed-out foreground call is not a failure to retry.** Its code keeps running and its kernel stays busy (`list-kernels` shows it): the next call to the default kernel runs in a temporary kernel without your variables, and a named kernel refuses until it is free. Re-issuing the work starts a *second* run — over the same output paths — which for tasks with "output already exists" guards then errors confusingly. Inspect the log/output first; stop the stray run with `interrupt-kernel` if needed.
- **Keep the launching call itself short.** Do setup (writing the script, `pip install`, staging inputs) in their own quick calls; the call that starts the long job should do little more than `nohup … &`.
- **Poll on a sensible cadence**, and surface progress from the log to the user rather than sitting silent. Consider having the script emit progress lines it can tail.
- **Redirect state that needs the environment** (`OBI_VLAB_ID`, `OBI_PROJECT_ID`, tokens) is read at launch time; if you background a job in a redirected project, pass the same `vlab_id`/`project_id` (and `sandbox_number`) on the launching call so it runs in the intended pod.
