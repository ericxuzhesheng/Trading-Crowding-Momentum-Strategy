"""Exercise publication against real local Git repositories, injecting transport faults."""

from pathlib import Path
import subprocess

import pytest

from scripts import publish_market_data as publisher


def run_git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True,
        text=True, encoding="utf-8",
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    local = tmp_path / "local"
    remote.mkdir()
    local.mkdir()
    run_git(remote, "init", "--bare", "--initial-branch=main")
    run_git(local, "init", "--initial-branch=main")
    run_git(local, "config", "user.name", "Test")
    run_git(local, "config", "user.email", "test@example.com")
    (local / "README.md").write_text("old\n")
    (local / "config.yaml").write_text("end_date: pinned\n")
    run_git(local, "add", ".")
    run_git(local, "commit", "-m", "baseline")
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    monkeypatch.chdir(local)
    monkeypatch.setattr(publisher.time, "sleep", lambda _: None)
    return local, remote


def change_outputs(local):
    (local / "README.md").write_text("new\n")
    (local / "config.yaml").write_text("end_date: null\n")
    panel = local / "data/processed/panel_daily.parquet"
    panel.parent.mkdir(parents=True)
    panel.write_bytes(b"PAR1\x00\xff\x00test")


def inject_push(monkeypatch, behavior):
    actual = publisher.git
    calls = []

    def wrapped(*args, **kwargs):
        if args[0] == "push":
            calls.append(args)
            return behavior(actual, args, kwargs, len(calls))
        return actual(*args, **kwargs)

    monkeypatch.setattr(publisher, "git", wrapped)
    return calls


def failed_push(args):
    return subprocess.CompletedProcess(args, 1, "Everything up-to-date\n", "HTTP 408 / remote hung up\n")


def test_publish_excludes_dirty_config_and_backs_up_binary_patch(repo):
    local, remote = repo
    change_outputs(local)
    commit = publisher.publish("main")
    assert run_git(remote, "rev-parse", "main") == commit
    assert run_git(remote, "show", "main:config.yaml") == "end_date: pinned"
    assert run_git(local, "diff", "--name-only") == "config.yaml"
    patch = local / "outputs/reports/publication.patch"
    assert "GIT binary patch" in patch.read_text()
    assert "config.yaml" not in patch.read_text()
    assert commit in (local / "outputs/reports/publication.json").read_text()
    run_git(local, "apply", "--reverse", "--check", str(patch))


def test_transient_failure_retries(repo, monkeypatch):
    local, remote = repo
    change_outputs(local)
    calls = inject_push(monkeypatch, lambda actual, args, kwargs, n:
                        failed_push(args) if n == 1 else actual(*args, **kwargs))
    commit = publisher.publish("main")
    assert len(calls) == 2
    assert run_git(remote, "rev-parse", "main") == commit


@pytest.mark.parametrize("timeout", [False, True])
def test_accepted_push_with_client_error_is_not_repeated(repo, monkeypatch, timeout):
    local, remote = repo
    change_outputs(local)

    def accepted(actual, args, kwargs, n):
        actual(*args, **kwargs)
        if timeout:
            raise subprocess.TimeoutExpired("git push", 120)
        return failed_push(args)

    calls = inject_push(monkeypatch, accepted)
    commit = publisher.publish("main")
    assert len(calls) == 1
    assert run_git(remote, "rev-parse", "main") == commit


def test_permanent_failure_is_bounded_and_preserves_recovery(repo, monkeypatch):
    local, remote = repo
    base = run_git(remote, "rev-parse", "main")
    change_outputs(local)
    calls = inject_push(monkeypatch, lambda actual, args, kwargs, n: failed_push(args))
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        publisher.publish("main")
    assert len(calls) == 3
    assert run_git(remote, "rev-parse", "main") == base
    assert (local / "outputs/reports/publication.patch").is_file()
    assert (local / "README.md").read_text() == "new\n"


def advance_remote(local, remote):
    other = local.parent / "other"
    run_git(local.parent, "clone", str(remote), str(other))
    run_git(other, "config", "user.name", "Other")
    run_git(other, "config", "user.email", "other@example.com")
    (other / "README.md").write_text("concurrent update\n")
    run_git(other, "add", "README.md")
    run_git(other, "commit", "-m", "concurrent update")
    run_git(other, "push", "origin", "main")
    return run_git(remote, "rev-parse", "main")


@pytest.mark.parametrize("during_push", [False, True])
def test_remote_conflict_never_overwrites_other_commit(repo, monkeypatch, during_push):
    local, remote = repo
    change_outputs(local)
    competing = []

    def push(actual, args, kwargs, n):
        if during_push:
            competing.append(advance_remote(local, remote))
        return actual(*args, **kwargs)

    if not during_push:
        competing.append(advance_remote(local, remote))
    calls = inject_push(monkeypatch, push)
    with pytest.raises(RuntimeError, match="advanced independently"):
        publisher.publish("main")
    assert len(calls) == int(during_push)
    assert run_git(remote, "rev-parse", "main") == competing[0]
    assert all("--force" not in call and not any(a.startswith("+") for a in call) for call in calls)


def test_no_changes_ignores_runtime_config_without_network(repo, monkeypatch):
    local, remote = repo
    base = run_git(local, "rev-parse", "HEAD")
    (local / "config.yaml").write_text("end_date: null\n")
    actual = publisher.git

    def offline(*args, **kwargs):
        assert args[0] not in ("push", "fetch")
        return actual(*args, **kwargs)

    monkeypatch.setattr(publisher, "git", offline)
    assert publisher.publish("main") is None
    assert run_git(local, "rev-parse", "HEAD") == base


def test_unknown_remote_state_does_not_push(repo, monkeypatch):
    local, remote = repo
    change_outputs(local)
    actual = publisher.git
    fetches = []

    def offline(*args, **kwargs):
        assert args[0] != "push"
        if args[0] == "fetch":
            fetches.append(args)
            raise subprocess.TimeoutExpired("git fetch", 120)
        return actual(*args, **kwargs)

    monkeypatch.setattr(publisher, "git", offline)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        publisher.publish("main")
    assert len(fetches) == 3


def test_remote_descendant_counts_as_published(repo):
    local, remote = repo
    change_outputs(local)
    commit = publisher.publish("main")
    advance_remote(local, remote)
    assert publisher.remote_state(commit, "main") == "published"


def test_preexisting_staged_changes_are_rejected(repo):
    local, remote = repo
    change_outputs(local)
    run_git(local, "add", "config.yaml")
    with pytest.raises(RuntimeError, match="pre-existing staged"):
        publisher.publish("main")
    assert run_git(local, "diff", "--cached", "--name-only") == "config.yaml"
