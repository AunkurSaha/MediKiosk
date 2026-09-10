import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
secrets = set()
for filename in ["backend/.env", ".env"]:
    for key, value in dotenv_values(root / filename).items():
        if not value:
            continue
        if (
            re.search(r"KEY|SECRET|PASSWORD|TOKEN", key, re.IGNORECASE)
            and len(value) >= 8
        ):
            secrets.add(value.encode())
        if "DATABASE_URL" in key:
            password = urlsplit(value).password
            if password and len(password) >= 8:
                secrets.add(unquote(password).encode())


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root)


paths = (
    git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    .decode()
    .split("\0")
)
matches = []
checked = 0
for name in filter(None, paths):
    path = root / name
    if not path.is_file():
        continue
    data = path.read_bytes()
    checked += 1
    if any(value in data for value in secrets):
        matches.append({"scope": "worktree", "path": name})
logs = list((root / ".runtime").glob("*.log"))
for path in logs:
    if any(value in path.read_bytes() for value in secrets):
        matches.append({"scope": "runtime-log", "path": path.name})
history_count = 0
objects = [
    line.partition(" ")
    for line in git("rev-list", "--objects", "--all").decode().splitlines()
]
batch = subprocess.run(
    ["git", "cat-file", "--batch"],
    cwd=root,
    input="".join(oid + "\n" for oid, _, _ in objects).encode(),
    capture_output=True,
    check=True,
).stdout
offset = 0
for oid, _, name in objects:
    end = batch.index(b"\n", offset)
    _, kind, length = batch[offset:end].split()
    offset = end + 1
    data = batch[offset : offset + int(length)]
    offset += int(length) + 1
    if kind == b"blob":
        history_count += 1
        if any(value in data for value in secrets):
            matches.append({"scope": "history", "object": oid, "path": name})
tracked_sensitive = [
    name
    for name in git("ls-files").decode().splitlines()
    if re.search(
        r"(^|/)(\.env(?!\.example)|\.runtime/|uploads/)|\.(pem|key|p12|pfx)$", name
    )
]
artifact = {
    "configured_secret_values_checked": len(secrets),
    "worktree_files": checked,
    "runtime_logs": len(logs),
    "history_blobs": history_count,
    "value_matches": matches,
    "tracked_sensitive_paths": tracked_sensitive,
    "limitation": "Configured-value and sensitive-path scan; cannot establish absence of unknown or removed credentials, PII or all security defects.",
}
(root / ".runtime/stabilization-secret-audit.json").write_text(
    json.dumps(artifact, indent=2)
)
print(json.dumps(artifact, indent=2))
raise SystemExit(bool(matches or tracked_sensitive))
