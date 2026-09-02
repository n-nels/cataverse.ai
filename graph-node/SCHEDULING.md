# Running the rebuild on a schedule

How to set `graph-node` up to rebuild the graph automatically. Written to be
followed on the machine itself, without reference to anything else.

Windows Task Scheduler, not cron — the target is a Windows box.

---

## What this does, and why there is no trigger in `orchestration/`

A rebuild reads the share drive and reconstructs the whole graph. It does not
need to be *told* an experiment finished; it works that out by comparing what
the sources imply against what the database holds.

So nothing in `orchestration/` changes. The lab PC's experiment code keeps
knowing nothing about Neo4j, and there is no way for a database problem to
affect a running experiment.

**Running early is harmless.** If a rebuild happens while the last spectrum fit
is still queued, that experiment loads without its `AdsParams` node and the next
rebuild adds it. Nothing is corrupted and nothing needs repairing — which is why
the interval does not have to be coordinated with the ~6 minute fit queue.

---

## 0. Which machine

It needs three things: the `X:` share drive mounted, network access to Aura, and
to be switched on when the task fires.

The obvious candidate is the PC running `orchestration/`, since it already has
`X:` and is always on.

One thing to be aware of rather than worried about: `.env` grants read-write
access to the graph, and Aura Free has no read-only user to fall back on. But
the graph is entirely derived from files on `X:`, so the worst case is that it
has to be rebuilt — minutes, not data loss. Nothing about the experiment data
itself is exposed. The only version where this matters is if the machine is
shared with people who should not be able to modify the graph.

---

## 1. Get the code onto that machine

Once `feature/graph-node` has been merged, `main` has everything and that is
what to use:

```powershell
cd C:\Users\<you>\Documents
git clone https://github.com/n-nels/cataverse.ai.git
cd cataverse.ai
```

If the repo is already there:

```powershell
git checkout main
git pull
```

Before the merge, use `git checkout feature/graph-node` instead. Either way,
confirm the package is present:

```powershell
Test-Path graph-node\SCHEDULING.md    # should print True
```

> This adds `graph-node/` and nothing else — the diff against `main` touches no
> file outside that directory, so it cannot disturb `orchestration/` or
> `ir-spectro-node/`.

---

## 2. Install `uv` if it is not already there

```powershell
uv --version
```

If that fails:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal afterwards so `uv` is on `PATH`.

---

## 3. Create the credentials file

`graph-node\.env` is deliberately **not** in git, so it has to be written on each
machine. Copy the example and fill it in:

```powershell
cd graph-node
Copy-Item .env.example .env
notepad .env
```

It needs four values plus the source root:

```
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<the password>
NEO4J_DATABASE=neo4j
SOURCE_ROOT=X:\peakFit
```

The same values the dashboard and the agent use. If you have `agent-node\.env`
on that machine already, the first four are identical.

---

## 4. Install dependencies and check it works

```powershell
cd graph-node
uv sync
uv run pytest -q
```

Expect 116 passing tests. They do not touch the database.

---

## 5. Do a dry run before scheduling anything

**Do not skip this.** It writes nothing, and it is how you find out that the
share drive path or the credentials are wrong before an unattended job does.

```powershell
.\scripts\rebuild.ps1 -DryRun
```

Read the output. What you want to see:

- A sensible number of experiment files found — hundreds, not zero.
- `Result: would apply cleanly, no deletions.` for both the data and the
  knowledge plan.

**If the delete column has large numbers, stop.** A rebuild deletes whatever its
sources do not account for, so large deletions almost always mean `SOURCE_ROOT`
is pointing at a subset of the data rather than the whole of `X:\peakFit`.

If it says `Source root does not exist`, the share drive is not mounted for this
user — see §8.

Once the dry run looks right, do one real run by hand and check it:

```powershell
.\scripts\rebuild.ps1
```

---

## 6. Create the scheduled task

Six hours is a reasonable interval: comfortably longer than the fit queue,
frequent enough that the graph is never far behind, and infrequent enough that
the logs stay readable. Experiments take three days, so there is no case for
running it often.

Run this in an **Administrator** PowerShell, editing the path:

```powershell
$Script = "C:\Users\<you>\Documents\cataverse.ai\graph-node\scripts\rebuild.ps1"

schtasks /Create `
  /TN "CataVerse graph rebuild" `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Script`"" `
  /SC HOURLY /MO 6 `
  /RL LIMITED `
  /F
```

By default this runs as the logged-in user, which matters: **mapped drives like
`X:` belong to a user session.** A task set to "run whether user is logged on or
not" often cannot see `X:` at all. If you hit that, see §8.

To confirm it registered:

```powershell
schtasks /Query /TN "CataVerse graph rebuild" /V /FO LIST
```

To run it immediately rather than waiting:

```powershell
schtasks /Run /TN "CataVerse graph rebuild"
```

---

## 7. Checking on it

Every run writes a timestamped log to `graph-node\logs\`. The most recent:

```powershell
cd graph-node
Get-ChildItem logs\rebuild_*.log | Sort-Object LastWriteTime -Desc |
  Select-Object -First 1 | Get-Content
```

Task Scheduler's own view of the last outcome:

```powershell
schtasks /Query /TN "CataVerse graph rebuild" /V /FO LIST |
  Select-String "Last Run Time","Last Result"
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Applied |
| 1 | Source data has errors, or the sweep refused — read the log |
| 2 | Source root missing or empty — usually `X:` is not mounted |

**The failure worth watching for is silence.** A task that stopped running looks
identical to a graph with no new experiments. The cheapest habit: when you next
look at cataverse.ai and expect to see a recent experiment and do not, check the
newest file in `logs\` before assuming anything else is wrong.

---

## 8. If the scheduled task cannot see `X:`

The commonest failure. A drive letter mapped in your desktop session does not
exist for a task running in another context.

Two fixes, in order of preference:

**Use the UNC path instead of the drive letter.** Mapped drives are per-session;
UNC paths are not. Find what `X:` points at:

```powershell
(Get-PSDrive X).DisplayRoot
```

Then set that in `.env`, keeping the `peakFit` folder:

```
SOURCE_ROOT=\\server\share\peakFit
```

Re-run the dry run to confirm. This is the more robust option and avoids the
whole class of problem.

**Or make the task run only when you are logged in.** In Task Scheduler, open
the task's properties and select "Run only when user is logged on". The mapped
drive then exists, but the rebuild stops happening when you sign out.

---

## 9. Changing or removing it

```powershell
# change the interval to every 12 hours
schtasks /Change /TN "CataVerse graph rebuild" /RI 720

# stop it entirely
schtasks /Delete /TN "CataVerse graph rebuild" /F
```

Deleting the task has no effect on the graph — it just stops updating. Rebuilds
can always be run by hand with `.\scripts\rebuild.ps1`.

---

## 10. Updating the code later

```powershell
cd cataverse.ai
git pull
cd graph-node
uv sync
.\scripts\rebuild.ps1 -DryRun
```

Always dry run after pulling. The scheduled task picks up the new code on its
next fire; nothing needs re-registering.
