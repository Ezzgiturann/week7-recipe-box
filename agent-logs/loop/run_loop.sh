#!/usr/bin/env bash
# Generator–critic loop orchestrator.
# Generator: one Claude Code session, resumed each round (keeps its memory).
# Critic:    a fresh Claude Code session each round, read-only tools.
# Each generator round is committed so the revisions are visible in git history.
set -uo pipefail

L=/Users/ezgi/week7-recipe-box/agent-logs/loop
WT=/Users/ezgi/recipe-task-c
VENV=/Users/ezgi/week7-recipe-box/.venv/bin
MAX_ROUNDS=5
export PATH="$VENV:$PATH"
cd "$WT"

GEN_TOOLS="Read,Edit,Write,Glob,Grep,Bash(pytest*),Bash(python*)"
CRITIC_TOOLS="Read,Glob,Grep,Bash(git diff*),Bash(git log*),Bash(pytest*)"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$L/timeline.txt"; }
result_of() { jq -r 'select(.type=="result") | .result' "$1"; }
session_of() { jq -r 'select(.type=="result") | .session_id' "$1"; }

: > "$L/timeline.txt"
session=""

for round in $(seq 1 "$MAX_ROUNDS"); do
  # ---- Generator ----
  if [ "$round" -eq 1 ]; then
    gen_prompt="$(cat "$L/generator-prompt.txt")"
    resume=()
  else
    gen_prompt="Bir code reviewer (critic) kodunu inceledi ve REVISE kararı verdi. Raporu aşağıda.
Her FAIL bulgusunu ele al: geçerliyse düzelt ve gerekirse test ekle; katılmıyorsan nedenini açıkla.
Orijinal görevdeki kurallar ve kapsam aynen geçerli (sadece main.py ve test_main.py, geçici veritabanı, commit atma). pytest geçmeli.
Sonunda hangi bulguyu nasıl ele aldığını madde madde özetle.

--- CRITIC RAPORU (round $((round - 1))) ---
$(cat "$L/round$((round - 1))-critic.md")"
    resume=(--resume "$session")
  fi
  log "round $round: generator START"
  # ${arr[@]+...} form: macOS bash 3.2 treats an empty array as unbound under set -u
  claude -p "$gen_prompt" ${resume[@]+"${resume[@]}"} --permission-mode acceptEdits \
    --allowedTools "$GEN_TOOLS" --output-format stream-json --verbose \
    < /dev/null > "$L/round$round-generator.jsonl" 2> "$L/round$round-generator.err"
  session="$(session_of "$L/round$round-generator.jsonl")"
  result_of "$L/round$round-generator.jsonl" > "$L/round$round-generator.md"
  log "round $round: generator END (session $session)"

  git add main.py test_main.py
  git commit -q -m "Scaling: generator round $round" \
    -m "Generator output for round $round of the generator-critic loop." \
    -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" || log "round $round: nothing to commit"
  log "round $round: committed $(git rev-parse --short HEAD)"

  # ---- Critic (fresh session) ----
  critic_prompt="$(cat "$L/critic-rubric.txt")

--- İNCELENECEK GÖREV (generator'a verilen prompt) ---
$(cat "$L/generator-prompt.txt")

--- NASIL İNCELEYECEKSİN ---
Değişiklikler bu branch'te commit edildi. Diff'i görmek için: git diff main...HEAD
Dosyaları okuyabilir ve pytest çalıştırabilirsin. Dosya düzenleme yetkin yok."
  log "round $round: critic START"
  claude -p "$critic_prompt" --allowedTools "$CRITIC_TOOLS" \
    --output-format stream-json --verbose \
    < /dev/null > "$L/round$round-critic.jsonl" 2> "$L/round$round-critic.err"
  result_of "$L/round$round-critic.jsonl" > "$L/round$round-critic.md"
  verdict="$(grep -oE 'VERDICT: (APPROVE|REVISE)' "$L/round$round-critic.md" | tail -1)"
  log "round $round: critic END -> ${verdict:-NO VERDICT}"

  if [ "$verdict" = "VERDICT: APPROVE" ]; then
    log "LOOP DONE: approved in round $round"
    exit 0
  fi
  if [ -z "$verdict" ]; then
    log "LOOP STOPPED: critic gave no verdict in round $round"
    exit 2
  fi
done
log "LOOP STOPPED: no approval after $MAX_ROUNDS rounds"
exit 1
