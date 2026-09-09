"""Legacy entry point. The maintained HTTP tests live under tests/."""
import subprocess
import sys

if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"]))

