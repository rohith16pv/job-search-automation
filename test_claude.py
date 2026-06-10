"""Quick Claude CLI validator. Run: python test_claude.py"""
from dotenv import load_dotenv
load_dotenv()

from core.claude_client import _claude_call, is_claude_available, SCORING_MODEL, TAILORING_MODEL

if not is_claude_available():
    print("ERROR: `claude` CLI not found on PATH.")
    print("Install Claude Code (https://claude.com/claude-code), then run `claude` once to log in.")
    raise SystemExit(1)

print(f"Testing claude CLI — scoring model: {SCORING_MODEL} | tailoring model: {TAILORING_MODEL}")

try:
    result = _claude_call(
        "You are a test bot. Return only valid JSON.",
        'Reply with exactly the JSON: {"status": "OK"}',
        max_retries=1,
    )
    print(f"SUCCESS: {result}")
    print("Claude is working — scoring and tailoring will use your Claude subscription.")
except Exception as e:
    print(f"FAIL — raw error:\n{e}")
    print("\nIf this is a 401/auth error, open a terminal, run `claude`, and log in")
    print("with your Claude subscription account, then re-run this test.")
    raise SystemExit(1)
