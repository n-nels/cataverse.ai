# Autoresearch Agent Profile (opencode.json)

Add this agent entry to the repo's `opencode.json` to grant the autoresearch loop
the autonomy it needs (git commit/discard, file edits) **scoped to a dedicated
agent only**. Default agents (coder, architect, etc.) stay restrictive so normal
work can't accidentally commit to main or rewrite history.

## Why a dedicated agent

The spec says the agent "must not ask for permission between normal iterations"
during the loop. But broadening `git *` to `"allow"` globally would let any
session commit to `main`. A dedicated `autoresearch` agent profile solves this:
it has the perms the loop needs; other agents don't.

Note: opencode permission rules are glob-based on the command string, not
branch-aware — `git *` can't distinguish "commit on autoresearch/v1" from "commit
on main." The **harness code** (`gitstate.py`) enforces the branch check in code
(`assert_autoresearch_branch`, refuses destructive ops off-branch). The
permission rule is belt-and-suspenders; the harness is the real guardrail.

## Snippet

Add this under the `"agent"` key in `opencode.json`, alongside existing agents:

```json
"autoresearch": {
  "description": "Runs bounded autonomous hyperparameter optimization campaigns. Drives the outer loop: run campaign, observe, reason, adjust, repeat.",
  "mode": "primary",
  "model": "opencode-go/glm-5.2",
  "temperature": 0.3,
  "permission": {
    "edit": "allow",
    "bash": {
      "*": "allow",
      "git *": "allow",
      "uv pip install *": "allow"
    }
  },
  "disable": false
}
```

## Notes

- **`model` / `temperature`:** match the repo's other primary agents, or tune
  for the optimization task. Higher temperature (0.3-0.5) encourages exploration
  between campaigns; lower (0.1-0.2) for deterministic execution.
- **`edit: "allow"`:** the loop writes `current_candidate.yaml`, manifests,
  artifacts, and edits model code between campaigns. Asking per-edit breaks
  autonomy.
- **`git *: "allow"`:** the loop commits candidate configs and discards via
  `git reset --hard` on the autoresearch branch. The harness refuses these ops
  off-branch.
- **`uv pip install *: "allow"`:** the loop may install missing model deps
  (ForestDiffusion, torch, etc.) per the spec's Dependency Installation policy.
- **Default agents unchanged:** do NOT modify the `coder`, `architect`, or other
  existing agent entries. Only add this new one.

## Invocation

When the user wants to run a real campaign, they switch to the autoresearch
agent (or the session uses it as the default for that task). The agent then:
1. Creates the `autoresearch/<run-tag>` branch.
2. Runs `python autoresearch.py --manifest <path> --git`.
3. Observes, reasons, adjusts, repeats within budget.
4. Writes the final report and leaves the repo clean.