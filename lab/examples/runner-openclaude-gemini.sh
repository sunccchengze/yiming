#!/usr/bin/env bash
# runner-openclaude-gemini.sh
#
# A drop-in "--runner" wrapper for the Yiming Council that answers every
# seat / reviewer / chair prompt through the OpenClaude CLI
# (https://github.com/Gitlawb/openclaude) pointed at Google Gemini.
#
# Gemini uses an API key only (no Anthropic hijacking), so it's the cheapest
# path for the roundtable — a free Google AI Studio key works here.
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
#   2. Configure the Gemini provider (any of):
#        export CLAUDE_CODE_USE_GEMINI=1
#        export GEMINI_API_KEY="$GEMINI_KEY"        # your free Google AI Studio key
#        export GEMINI_MODEL="gemini-3-flash-preview"  # or e.g. gemini-2.5-flash
#      OR run `openclaude` and use `/provider` to save a Gemini profile.
#      (GEMINI_BASE_URL defaults to generativelanguage.googleapis.com; set it
#       only if you use Vertex AI.)
#   3. Verify once:  echo "hi" | openclaude --print
#
# Usage:
#   python -m lab council run --run <RUN_DIR> --execute \
#     --runner "$(pwd)/lab/examples/runner-openclaude-gemini.sh" \
#     --workers 4 --timeout-seconds 900
#
set -euo pipefail

PROMPT="$(cat)"

stage="${YIMING_PROMPT_STAGE:-independent-seat}"
echo "[runner-openclaude-gemini] stage=${stage} prompt_chars=${#PROMPT}" >&2

# --print             non-interactive mode; reads the prompt from stdin
# --output-format text (default) plain assistant text, what the council parses
# --thinking disabled  skip hidden reasoning for cheap batch seat calls
exec openclaude --print \
  --output-format text \
  --thinking disabled
