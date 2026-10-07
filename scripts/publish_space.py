"""Publish (or update) the app's Hugging Face Space.

Uploads exactly the files that git tracks at the current commit, nothing else,
so local secrets (.env), WAV masters and the Python environment can never be
sent. The Space is created private unless ``--public`` is given. Re-run it after
committing to update the Space; Reachy Mini Control then offers the update.

Usage::

    python scripts/publish_space.py                 # create/update, private
    python scripts/publish_space.py --public        # make it public
    python scripts/publish_space.py --dry-run       # list what would be uploaded

Needs a Hugging Face login with write access: ``hf auth login``.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi

PROJECT_DIR = Path(__file__).resolve().parent.parent
SPACE_NAME = "reachy_meets_planck"
FORBIDDEN = (".env",)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_DIR, check=True, capture_output=True, text=True
    ).stdout


def tracked_files() -> list[str]:
    files = git("ls-files").splitlines()
    leaked = [
        f for f in files
        if Path(f).name in FORBIDDEN
        or (Path(f).name.startswith(".env.") and not f.endswith(".env.example"))
    ]
    if leaked:
        sys.exit(f"Refusing to publish: secret files are tracked by git: {leaked}")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument("--public", action="store_true", help="make the Space public")
    visibility.add_argument("--private", action="store_true", help="make the Space private")
    parser.add_argument("--dry-run", action="store_true", help="list files, upload nothing")
    args = parser.parse_args()

    if git("status", "--porcelain"):
        sys.exit("Commit your changes first: the Space must match a git commit.")
    files = tracked_files()
    commit = git("rev-parse", "--short", "HEAD").strip()
    subject = git("log", "-1", "--format=%s").strip()
    size = sum((PROJECT_DIR / f).stat().st_size for f in files)
    print(f"{len(files)} tracked files, {size / 1e6:.1f} MB, from commit {commit}: {subject}")
    if args.dry_run:
        print("\n".join(f"  {f}" for f in files if not f.endswith(".ogg")))
        print(f"  ... plus {sum(f.endswith('.ogg') for f in files)} .ogg clips")
        return

    api = HfApi()
    repo_id = f"{api.whoami()['name']}/{SPACE_NAME}"
    created = not api.repo_exists(repo_id, repo_type="space")
    if created:
        api.create_repo(repo_id, repo_type="space", space_sdk="static", private=not args.public)
        print(f"Created {'public' if args.public else 'private'} Space {repo_id}")
    elif args.public or args.private:
        api.update_repo_settings(repo_id, repo_type="space", private=args.private)
        print(f"Space {repo_id} is now {'private' if args.private else 'public'}")

    # Delete files that are no longer tracked, then add every tracked file.
    remote = set(api.list_repo_files(repo_id, repo_type="space"))
    stale = sorted(remote - set(files) - {".gitattributes"})
    if stale:
        api.delete_files(repo_id, stale, repo_type="space",
                         commit_message=f"Remove files no longer in {commit}")
    operations = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=str(PROJECT_DIR / f))
                  for f in files]
    api.create_commit(repo_id, operations, repo_type="space",
                      commit_message=f"{subject} (GitHub {commit})")
    print(f"Uploaded {len(files)} files: https://huggingface.co/spaces/{repo_id}")


if __name__ == "__main__":
    main()
