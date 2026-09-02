#!/usr/bin/env bash
# runner-openclaude-deepseek.sh
#
# A drop-in "--runner" wrapper for the Yiming Council that answers every
# seat / reviewer / chair prompt through the OpenClaude CLI
# (https://github.com/Gitlawb/openclaude) pointed at DeepSeek.
#
# Why this instead of `claude -p`? OpenClaude is a Claude Code-style CLI that
# natively supports OpenAI-compatible backends, so pointing it at DeepSeek is a
# first-class path (no hijacking Anthropic's endpoint).
#
# How it works:
#   - The council pipes each prompt to this script's stdin. We hand it to
#     `openclaude --print` (OpenClaude's non-interactive print mode), which
#     accepts the prompt from stdin.
#   - The stage (independent-seat | blind-reviewer | chair) is available in
#     $YIMING_PROMPT_STAGE so you can special-case if you want.
#
# Prerequisites (once, on YOUR machine):
#   1. Install OpenClaude:  npm install -g @gitlawb/openclaude@latest
#   2. Configure the DeepSeek OpenAI-compatible endpoint (any of):
#        export CLAUDE_CODE_USE_OPENAI=1
#        export OPENAI_BASE_URL="https://api.deepseek.com"
#        export OPENAI_API_KEY="$DEEPSEEK_API_KEY"     # your DeepSeek key
#        export OPENAI_MODEL="deepseek-chat"
#      OR run `openclaude` and use `/provider` to save a profile.
#   3. Verify once:  echo "hi" | openclaude --print
#
# Usage:
#   python -m lab council run --run <RUN_DIR> --execute \
#     --runner "$(pwd)/lab/examples/runner-openclaude-deepseek.sh" \
#     --workers 4 --timeout-seconds 900
#
set -euo pipefail

PROMPT="$(cat)"

stage="${YIMING_PROMPT_STAGE:-independent-seat}"
echo "[runner-openclaude-deepseek] stage=${stage} prompt_chars=${#PROMPT}" >&2

# --print             non-interactive mode; reads the prompt from stdin
# --output-format text (default) plain assistant text, what the council parses
# --thinking disabled  skip hidden reasoning for cheap batch seat calls
exec openclaude --print \
  --output-format text \
  --thinking disabled
