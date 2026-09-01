#!/usr/bin/env bash
# runner-claude-deepseek.sh
#
# A drop-in "--runner" wrapper for the Yiming Council that answers every
# seat / reviewer / chair prompt through the Claude Code CLI pointed at
# DeepSeek. This lets the roundtable run on DeepSeek without DeepTutor.
#
# How it works:
#   - The council writes each prompt to a .md file AND pipes it to this
#     script's stdin. We read the prompt from stdin and pass it to `claude -p`.
#   - The stage (independent-seat | blind-reviewer | chair) is available in
#     $YIMING_PROMPT_STAGE so you can special-case if you want.
#
# Prerequisites (once, on YOUR machine):
#   1. Install the Claude Code CLI:   npm i -g @anthropic-ai/claude-code
#   2. Point it at DeepSeek's Anthropic-compatible endpoint:
#        export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
#        export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"   # your DeepSeek key
#        export ANTHROPIC_MODEL="deepseek-chat"            # or deepseek-reasoner
#      (verify once with:  echo "hi" | claude -p --output-format text)
#
# Usage:
#   python -m lab council run --run <RUN_DIR> --execute \
#     --runner "$(pwd)/lab/examples/runner-claude-deepseek.sh" \
#     --workers 4 --timeout-seconds 900
#
set -euo pipefail

# Prompt arrives on stdin (the council always pipes it to the runner).
PROMPT="$(cat)"

stage="${YIMING_PROMPT_STAGE:-independent-seat}"
echo "[runner-claude-deepseek] stage=${stage} prompt_chars=${#PROMPT}" >&2

# Send it to the Claude Code CLI. The council wants plain text on stdout so it
# can parse the <ballot> blocks and the chair memo headings.
#   -p <text>                run in non-interactive print mode
#   --output-format text     emit the raw assistant text (not JSON)
#   --dangerously-skip-permissions  avoid permission prompts in batch mode
exec claude -p "$PROMPT" \
  --output-format text \
  --dangerously-skip-permissions
