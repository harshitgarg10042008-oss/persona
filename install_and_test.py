"""
Run this with the venv python to install groq and do a live API test.
Usage: python install_and_test.py
"""
import subprocess
import sys
import os

print("=" * 60)
print("Python executable:", sys.executable)
print("=" * 60)

# ── 1. Install groq ──────────────────────────────────────────
print("\n[1] Installing groq via pip...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "--upgrade", "groq"],
    text=True, capture_output=True
)
print("STDOUT:", result.stdout or "(empty)")
print("STDERR:", result.stderr or "(empty)")
print("Return code:", result.returncode)

# ── 2. Confirm import ────────────────────────────────────────
print("\n[2] Importing groq...")
try:
    import groq
    print("OK — groq version:", groq.__version__)
    from groq import Groq
    print("OK — Groq class imported:", Groq)
except ImportError as e:
    print("FAILED to import groq:", e)
    sys.exit(1)

# ── 3. Load API key ──────────────────────────────────────────
print("\n[3] Loading GROQ_API_KEY from .env...")
try:
    from decouple import config
    api_key = config("GROQ_API_KEY", default=None)
except Exception:
    api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    print("ERROR: GROQ_API_KEY is empty or not set!")
    sys.exit(1)

print(f"API key loaded OK. First 8 chars: {api_key[:8]}...")

# ── 4. Live Groq API test ─────────────────────────────────────
print("\n[4] Making a live Groq API call (simple test prompt)...")
model = "llama-3.3-70b-versatile"
print(f"Model: {model}")

try:
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": "Reply with exactly: {\"ok\": true}"}],
        model=model,
        timeout=30,
    )
    print("\nRAW RESPONSE OBJECT:")
    print(response)
    print()

    content = response.choices[0].message.content
    print("Content:", repr(content))

    if content and content.strip():
        print("\nSUCCESS — Groq API is working correctly!")
    else:
        print("\nWARNING — API call succeeded but content is empty!")

except Exception as e:
    print(f"\nERROR during API call: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("Done.")
print("=" * 60)
