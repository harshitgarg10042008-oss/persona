import sys
import subprocess

print("Python executable:", sys.executable)
print()

# Check if groq is importable
try:
    import groq
    print("groq is INSTALLED, version:", groq.__version__)
except ImportError as e:
    print("groq is NOT installed:", e)
    print()
    print("Installing groq now...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "groq"],
        capture_output=True, text=True
    )
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print()
    try:
        import groq
        print("groq installed successfully, version:", groq.__version__)
    except ImportError as e2:
        print("STILL failed to import groq:", e2)

print()
print("All installed packages related to groq/google:")
result = subprocess.run(
    [sys.executable, "-m", "pip", "list"],
    capture_output=True, text=True
)
for line in result.stdout.splitlines():
    if any(k in line.lower() for k in ["groq", "google", "generative"]):
        print(" ", line)
