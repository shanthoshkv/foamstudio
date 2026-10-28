"""SSH transport through the system OpenSSH client. No paramiko and no asyncssh."""

from __future__ import annotations

from foamstudio.core.runtime.model import Installation
from foamstudio.core.runtime.paths import bash_command


def _reject(label: str, value: str) -> None:
    if "$" in value:
        raise ValueError(
            f"The SSH {label} contains '$' ({value}). "
            "Rename it. FoamStudio does not expand shell variables in SSH paths."
        )


def ssh_argv(
    installation: Installation,
    command: str,
    env: dict[str, str] | None = None,
) -> tuple[tuple[str, ...], str]:
    remote = installation.remote_case or "/case"
    _reject("host", installation.host)
    _reject("user", installation.user)
    _reject("remote case", remote)
    _reject("bashrc", installation.bashrc)
    body = bash_command(installation.bashrc, remote, command, env)
    argv = (
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{installation.user}@{installation.host}",
        "bash",
        "-lc",
        body,
    )
    return argv, body


def push_argv(installation: Installation, local: str, remote: str) -> tuple[str, ...]:
    _reject("host", installation.host)
    _reject("user", installation.user)
    _reject("local path", local)
    _reject("remote path", remote)
    target = f"{installation.user}@{installation.host}:{remote}"
    return ("scp", "-o", "BatchMode=yes", "-r", local, target)


def pull_argv(installation: Installation, remote: str, local: str) -> tuple[str, ...]:
    _reject("host", installation.host)
    _reject("user", installation.user)
    _reject("remote path", remote)
    _reject("local path", local)
    source = f"{installation.user}@{installation.host}:{remote}"
    return ("scp", "-o", "BatchMode=yes", "-r", source, local)


def slurm_script(
    installation: Installation,
    command: str,
    *,
    ntasks: int = 4,
    time_limit: str = "01:00:00",
    job_name: str = "foamstudio",
) -> str:
    remote = installation.remote_case or "/case"
    _reject("remote case", remote)
    return (
        "#!/bin/bash\n"
        f"#SBATCH --job-name={job_name}\n"
        f"#SBATCH --ntasks={ntasks}\n"
        f"#SBATCH --time={time_limit}\n"
        f"#SBATCH --output=log.slurm\n"
        f"source {installation.bashrc}\n"
        f"cd {remote}\n"
        f"srun {command}\n"
    )


def pbs_script(
    installation: Installation,
    command: str,
    *,
    ncpus: int = 4,
    walltime: str = "01:00:00",
    job_name: str = "foamstudio",
) -> str:
    remote = installation.remote_case or "/case"
    _reject("remote case", remote)
    return (
        "#!/bin/bash\n"
        f"#PBS -N {job_name}\n"
        f"#PBS -l select=1:ncpus={ncpus}\n"
        f"#PBS -l walltime={walltime}\n"
        f"#PBS -j oe\n"
        f"source {installation.bashrc}\n"
        f"cd {remote}\n"
        f"mpirun -np {ncpus} {command}\n"
    )


def trame_script(foam_file: str) -> str:
    """Optional remote view. trame is not a FoamStudio dependency."""
    if "$" in foam_file:
        raise ValueError("The remote view path contains '$'. Rename the case folder.")
    quoted = foam_file.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "#!/usr/bin/env python3\n"
        '"""Optional trame viewer. Install trame yourself; FoamStudio does not depend on it."""\n'
        "try:\n"
        "    from trame.app import get_server\n"
        "except ImportError as exc:\n"
        "    raise SystemExit(\n"
        '        "trame is not installed.\\n\\n"'
        '        "pip install trame trame-vuetify  then run this script again."\n'
        "    ) from exc\n"
        "server = get_server()\n"
        f'print("Open the case in the trame server: {quoted}")\n'
        "server.start()\n"
    )
