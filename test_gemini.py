"""Quick Groq key validator. Run: python test_gemini.py"""
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.environ.get("GROQ_API_KEY", "")
if not api_key:
    print("ERROR: GROQ_API_KEY not set in .env")
    print("Get a free key at: https://console.groq.com/keys")
    raise SystemExit(1)

print(f"Testing Groq key: {api_key[:8]}...{api_key[-4:]}")

try:
    from groq import Groq
except ImportError:
    print("ERROR: Run: pip install groq")
    raise SystemExit(1)

client = Groq(api_key=api_key)
try:
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": 'Reply with exactly the JSON: {"status": "OK"}'}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=20,
    )
    text = resp.choices[0].message.content
    print(f"SUCCESS: {text.strip()}")
    print("Groq key is valid. Free tier: 14,400 req/day, 30 RPM.")
except Exception as e:
    print(f"FAIL — raw error:\n{e}")
