You are running one iteration of an engineering loop. Work in the current directory.

1. Read PLAN.md, PROGRESS.md, DECISIONS.md and BLOCKERS.md (create the last two if missing).
2. Find the first task in PROGRESS.md that is not DONE or BLOCKED. If none remain, append the
   line ALL_TASKS_COMPLETE to PROGRESS.md and stop.
3. Do that one task completely. Run its PASS test for real and paste the real output into
   PROGRESS.md under the task. Mark it DONE only if the PASS condition truly holds.
4. If a long simulation is needed, start it with `timeout`, poll it, and work on independent
   sub-steps while it runs.
5. Commit, update PROGRESS.md, then stop. The outer loop starts the next iteration.

Rules: never ask questions or wait for input; record every judgment call in DECISIONS.md and
every dead end in BLOCKERS.md; read an OpenFOAM tutorial rather than guessing syntax; verify
every number before writing it anywhere; be honest about physics and failures.
