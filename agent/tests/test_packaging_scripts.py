import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_AGENT_VERSION = (REPO_ROOT / "agent/VERSION").read_text(encoding="utf-8").strip()


def _copy_packaging_tree(destination: Path) -> Path:
    repo_copy = destination / "repo"
    for relative_path in [
        "agent/README.md",
        "agent/VERSION",
        "agent/CHANGELOG.md",
        "agent/Dockerfile",
        "agent/__init__.py",
        "agent/grapheon_agent.py",
        "deploy/grapheon-agent.env.example",
        "deploy/grapheon-agent.service",
        "deploy/grapheon-agent.timer",
        "scripts/install-passive-agent.sh",
        "scripts/upgrade-passive-agent.sh",
        "scripts/rollback-passive-agent.sh",
        "scripts/uninstall-passive-agent.sh",
        "scripts/build-agent-artifact.sh",
        "docs/agent_quickstart.md",
    ]:
        source = REPO_ROOT / relative_path
        target = repo_copy / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return repo_copy


def _fake_systemctl(tmp_path: Path) -> Path:
    fake = tmp_path / "fake-systemctl"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$@\" >> \"$FAKE_SYSTEMCTL_LOG\"\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


def test_install_script_creates_versioned_release_and_current_symlink(tmp_path):
    repo_copy = _copy_packaging_tree(tmp_path)
    fake_systemctl = _fake_systemctl(tmp_path)
    systemctl_log = tmp_path / "systemctl.log"
    prefix = tmp_path / "prefix"
    state_dir = tmp_path / "state"
    env_dest = tmp_path / "grapheon-agent.env"
    systemd_dir = tmp_path / "systemd"

    result = subprocess.run(
        [
            "bash",
            str(repo_copy / "scripts/install-passive-agent.sh"),
            str(prefix),
            str(state_dir),
            str(env_dest),
            str(systemd_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SYSTEMCTL_BIN": str(fake_systemctl),
            "FAKE_SYSTEMCTL_LOG": str(systemctl_log),
        },
    )

    assert result.returncode == 0, result.stderr
    assert (prefix / f"agent/releases/{CURRENT_AGENT_VERSION}/grapheon_agent.py").exists()
    assert (
        prefix / f"agent/releases/{CURRENT_AGENT_VERSION}/VERSION"
    ).read_text().strip() == CURRENT_AGENT_VERSION
    assert (prefix / "agent/current").is_symlink()
    assert (prefix / "agent/current").resolve() == (
        prefix / f"agent/releases/{CURRENT_AGENT_VERSION}"
    )
    assert env_dest.exists()
    assert "daemon-reload" in systemctl_log.read_text(encoding="utf-8")


def test_rollback_script_repoints_current_symlink_to_previous_release(tmp_path):
    repo_copy = _copy_packaging_tree(tmp_path)
    fake_systemctl = _fake_systemctl(tmp_path)
    systemctl_log = tmp_path / "systemctl.log"
    prefix = tmp_path / "prefix"
    state_dir = tmp_path / "state"
    env_dest = tmp_path / "grapheon-agent.env"
    systemd_dir = tmp_path / "systemd"
    install_script = repo_copy / "scripts/install-passive-agent.sh"
    rollback_script = repo_copy / "scripts/rollback-passive-agent.sh"

    base_env = {
        **os.environ,
        "SYSTEMCTL_BIN": str(fake_systemctl),
        "FAKE_SYSTEMCTL_LOG": str(systemctl_log),
    }

    (repo_copy / "agent/VERSION").write_text("0.1.0\n", encoding="utf-8")
    first_install = subprocess.run(
        [
            "bash",
            str(install_script),
            str(prefix),
            str(state_dir),
            str(env_dest),
            str(systemd_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=base_env,
    )
    assert first_install.returncode == 0, first_install.stderr

    (repo_copy / "agent/VERSION").write_text("0.2.0\n", encoding="utf-8")
    second_install = subprocess.run(
        [
            "bash",
            str(install_script),
            str(prefix),
            str(state_dir),
            str(env_dest),
            str(systemd_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=base_env,
    )
    assert second_install.returncode == 0, second_install.stderr
    assert (prefix / "agent/current").resolve() == (prefix / "agent/releases/0.2.0")

    rollback = subprocess.run(
        [
            "bash",
            str(rollback_script),
            "0.1.0",
            str(prefix),
            str(systemd_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=base_env,
    )

    assert rollback.returncode == 0, rollback.stderr
    assert (prefix / "agent/current").resolve() == (prefix / "agent/releases/0.1.0")
    assert "daemon-reload" in systemctl_log.read_text(encoding="utf-8")
