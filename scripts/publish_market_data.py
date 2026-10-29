"""Publish only generated market data, with bounded, verified fast-forward pushes."""

import argparse
import json
from pathlib import Path
import subprocess
import time


OUTPUT_PATHS = (
    "data/processed/panel_daily.parquet",
    "outputs/figures/*.png",
    "outputs/tables/*.csv",
    "outputs/reports/backtest_report.md",
    "README.md",
)
ATTEMPTS = 3
GIT_TIMEOUT = 120


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=GIT_TIMEOUT,
    )
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result


def is_ancestor(older: str, newer: str) -> bool:
    result = git("merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Cannot verify ancestry: {result.stderr.strip()}")
    return result.returncode == 0


def remote_state(commit: str, branch: str) -> str:
    # Fetch objects as well as the ref: the remote may contain descendants of commit.
    git("fetch", "--no-tags", "origin", f"refs/heads/{branch}")
    remote = git("rev-parse", "FETCH_HEAD").stdout.strip()
    if is_ancestor(commit, remote):
        return "published"
    if is_ancestor(remote, commit):
        return "ready"
    return "diverged"


def push_verified(commit: str, branch: str) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        print(f"Publication attempt {attempt}/{ATTEMPTS}", flush=True)
        try:
            state = remote_state(commit, branch)
            if state == "ready":
                try:
                    result = git("push", "origin", f"{commit}:refs/heads/{branch}", check=False)
                    print(result.stdout + result.stderr, flush=True)
                except subprocess.TimeoutExpired:
                    print("Push timed out; checking whether the server accepted it.", flush=True)
                # Even a successful exit or 'Everything up-to-date' needs verification.
                state = remote_state(commit, branch)
            if state == "published":
                print(f"Verified remote {branch} contains {commit}", flush=True)
                return
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"Remote verification failed: {exc}", flush=True)
            state = "unknown"
        if state == "diverged":
            raise RuntimeError("Remote branch advanced independently; rerun from its latest head. No force push or rebase attempted.")
        if attempt < ATTEMPTS:
            time.sleep(10 * attempt)
    raise RuntimeError("Publication could not be verified after 3 attempts; inspect the recovery artifact and remote before retrying.")


def publish(branch: str) -> str | None:
    git("check-ref-format", f"refs/heads/{branch}")
    if git("diff", "--cached", "--name-only").stdout.strip():
        raise RuntimeError("Refusing to include pre-existing staged changes.")
    base = git("rev-parse", "HEAD").stdout.strip()
    # Enumerate tracked (including deleted) and new output files. config.yaml stays dirty.
    paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *OUTPUT_PATHS).stdout
    files = sorted(set(filter(None, paths.split("\0"))))
    if files:
        git("add", "--all", "--", *files)
    if not git("diff", "--cached", "--name-only").stdout.strip():
        print("No generated data changes to publish.")
        return None
    git(
        "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "--no-verify", "-m", "chore: auto-update market data to latest",
    )
    commit = git("rev-parse", "HEAD").stdout.strip()
    recovery = Path("outputs/reports")
    recovery.mkdir(parents=True, exist_ok=True)
    (recovery / "publication.json").write_text(
        json.dumps({"base": base, "commit": commit, "branch": branch}, indent=2) + "\n",
        encoding="utf-8",
    )
    (recovery / "publication.patch").write_text(
        git("diff", "--binary", base, commit, "--", *OUTPUT_PATHS).stdout,
        encoding="utf-8", newline="\n",
    )
    push_verified(commit, branch)
    return commit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", required=True)
    publish(parser.parse_args().branch)
