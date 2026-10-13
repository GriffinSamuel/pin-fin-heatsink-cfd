#!/usr/bin/env bash
# Runs Claude Code one task at a time until PROGRESS.md contains ALL_TASKS_COMPLETE.
# Permissions come from .claude/settings.json (scoped to this project; no sudo, no network).
# Usage, inside WSL Ubuntu with the laptop plugged in:   bash loop.sh
cd "$(dirname "$0")"
source /opt/openfoam14/etc/bashrc
mkdir -p logs
MAX_ITER=${MAX_ITER:-40}
for i in $(seq 1 $MAX_ITER); do
  if grep -q ALL_TASKS_COMPLETE PROGRESS.md; then echo "All tasks complete."; break; fi
  echo "=== iteration $i  $(date) ===" | tee -a logs/loop.log
  timeout 3h claude -p "$(cat LOOP_PROMPT.md)" --permission-mode acceptEdits \
    2>&1 | tee "logs/iter_$(printf %03d "$i").log" | tail -5
  git add -A >/dev/null 2>&1 && git commit -qm "loop iteration $i" >/dev/null 2>&1
  sleep 5
done
echo "Loop finished. See PROGRESS.md, BLOCKERS.md and logs/."
