"""Download one GGUF file from Hugging Face into LM Studio's model folder, verify it, and record it.

    python scripts/fetch_model.py <repo> <filename>
    python scripts/fetch_model.py mradermacher/XiYanSQL-QwenCoder-7B-2504-GGUF XiYanSQL-QwenCoder-7B-2504.Q4_K_M.gguf

Checks before it keeps the file: the size and SHA-256 must match what Hugging Face publishes for that file. The licence tag
is read from the repo metadata and written to docs/models.json next to the hash, so a run can always say exactly which file
it used. Resumes an interrupted download. Nothing is downloaded that was not named on the command line.
"""

import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LMS_MODELS = Path.home() / ".lmstudio" / "models"
MANIFEST = ROOT / "docs" / "models.json"
UA = {"User-Agent": "nlsql-lab"}


def hf_info(repo: str) -> dict:
    req = urllib.request.Request(f"https://huggingface.co/api/models/{repo}?blobs=true", headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=30))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    repo, filename = sys.argv[1], sys.argv[2]
    info = hf_info(repo)
    entry = next((s for s in info["siblings"] if s["rfilename"] == filename), None)
    if entry is None:
        print(f"{filename} is not in {repo}")
        return 2
    want_size, want_sha = entry["size"], (entry.get("lfs") or {}).get("sha256", "")
    licence = next((t.split(":", 1)[1] for t in info.get("tags", []) if t.startswith("license:")), "not stated in the repo metadata")
    dest_dir = LMS_MODELS / repo.split("/")[0] / repo.split("/")[1]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest, part = dest_dir / filename, dest_dir / (filename + ".part")
    print(f"{repo}/{filename}: {want_size / 1e9:.2f} GB, licence {licence}")
    if not dest.exists() or dest.stat().st_size != want_size:
        url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
        rc = subprocess.run(["curl.exe", "-L", "--fail", "-sS", "-C", "-", "-o", str(part), url]).returncode
        if rc != 0:
            print("download failed, curl exit", rc)
            return 3
        part.replace(dest)
    got = sha256_of(dest)
    if dest.stat().st_size != want_size or (want_sha and got != want_sha):
        print("VERIFY FAILED: size or sha256 does not match Hugging Face; deleting the file")
        dest.unlink()
        return 4
    print("verified: size and sha256 match")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest[f"{repo}/{filename}"] = {"repo": repo, "file": filename, "bytes": want_size, "sha256": got, "licence": licence,
                                     "repo_revision": info.get("sha", ""), "path_hint": str(dest.relative_to(LMS_MODELS))}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
