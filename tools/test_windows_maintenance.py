"""Exercise actual Windows PowerShell and Task Scheduler, without running cleanup."""
import os
from pathlib import Path
import subprocess
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows Task Scheduler')


def ps(*args):
    return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                           *map(str, args)], capture_output=True, text=True, timeout=45)


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def prepare(tmp_path):
    # Space and apostrophe are intentional: no generated shell command may break them.
    root = tmp_path / "Nova's clone"
    (root / '.git').mkdir(parents=True)
    (root / 'tools').mkdir()
    (root / 'scripts').mkdir()
    (root / 'tools/repo_hygiene.py').write_text('raise SystemExit(0)')
    (root / 'scripts/Invoke-NovaRepoHygiene.ps1').write_text('exit 0')
    return root


@pytest.mark.parametrize('code', [0, 1, 2])
def test_runner_preserves_python_result_and_log(tmp_path, code):
    root = prepare(tmp_path)
    (root / 'tools/repo_hygiene.py').write_text(
        f'import sys\nprint("diagnostic", file=sys.stderr)\nraise SystemExit({code})')
    result = ps('-File', ROOT / 'scripts/Invoke-NovaRepoHygiene.ps1', '-RepoRoot', root)
    assert result.returncode == code, result.stdout + result.stderr
    log = (root / 'logs/repo-hygiene.log').read_text(encoding='utf-8-sig')
    assert 'diagnostic' in log and f'result={code}' in log


def test_installer_skips_linked_worktree(tmp_path):
    root = tmp_path / 'linked'
    root.mkdir()
    (root / '.git').write_text('gitdir: elsewhere')
    result = ps('-File', ROOT / 'scripts/Ensure-NovaMaintenanceTask.ps1', '-RepoRoot', root)
    assert result.returncode == 0
    assert 'skipped' in result.stdout


def test_missing_maintenance_files_fail_visibly(tmp_path):
    (tmp_path / '.git').mkdir()
    result = ps('-File', ROOT / 'scripts/Ensure-NovaMaintenanceTask.ps1', '-RepoRoot', tmp_path)
    assert result.returncode == 2
    assert 'missing' in result.stdout


def test_real_task_install_idempotence_and_disabled_repair(tmp_path):
    root = prepare(tmp_path)
    name = 'NovaMaintenanceTest-' + uuid.uuid4().hex
    command = ['-File', ROOT / 'scripts/Ensure-NovaMaintenanceTask.ps1',
               '-RepoRoot', root, '-TaskName', name]
    try:
        installed = ps(*command, '-AtTime', '23:15')
        assert installed.returncode == 0, installed.stdout + installed.stderr
        assert 'installed and verified' in installed.stdout
        before = ps('-Command', f'Export-ScheduledTask -TaskName {quote(name)}').stdout
        repeated = ps(*command)
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr
        assert 'installed' not in repeated.stdout
        after = ps('-Command', f'Export-ScheduledTask -TaskName {quote(name)}').stdout
        assert before == after
        disabled = ps('-Command', f'Disable-ScheduledTask -TaskName {quote(name)} | Out-Null')
        assert disabled.returncode == 0, disabled.stderr
        repaired = ps(*command)
        assert repaired.returncode == 0, repaired.stdout + repaired.stderr
        assert 'installed and verified' in repaired.stdout
    finally:
        removed = ps('-Command', f'Unregister-ScheduledTask -TaskName {quote(name)} '
                     '-Confirm:$false -ErrorAction SilentlyContinue')
        assert removed.returncode == 0, removed.stderr
