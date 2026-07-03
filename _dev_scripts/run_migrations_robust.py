import subprocess

with open('migration_output.txt', 'w') as f:
    f.write("--- makemigrations ---\n")
    f.flush()
    result1 = subprocess.run(['.\\venv\\Scripts\\python.exe', 'manage.py', 'makemigrations', 'AnalysisAPI'], capture_output=True, text=True)
    f.write(f"STDOUT:\n{result1.stdout}\n")
    f.write(f"STDERR:\n{result1.stderr}\n")
    f.flush()
    
    f.write("\n--- migrate ---\n")
    f.flush()
    result2 = subprocess.run(['.\\venv\\Scripts\\python.exe', 'manage.py', 'migrate'], capture_output=True, text=True)
    f.write(f"STDOUT:\n{result2.stdout}\n")
    f.write(f"STDERR:\n{result2.stderr}\n")
    f.flush()

print("Migrations completed.")
