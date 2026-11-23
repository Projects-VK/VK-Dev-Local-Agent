"""Inicia os serviços de observabilidade selecionados na instalação."""

import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys

from iniciar_mellum import garantir_docker


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], encoding="utf-8", **kwargs)


def start_collector(folder):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise RuntimeError("pythonw.exe é necessário para o coletor de hardware.")
    script = r"""
$ErrorActionPreference = 'Stop'
$name = 'LLM Local - Coletor de hardware'
$folder = $env:VK_HARDWARE_FOLDER
$arguments = '-B "{0}" "{1}"' -f (Join-Path $folder 'exportar_hardware.py'), (Join-Path $folder 'hardware/llm.prom')
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Arguments -ne $arguments) { throw 'O coletor está configurado em outra pasta.' }
} else {
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $env:VK_HARDWARE_PYTHONW -Argument $arguments -WorkingDirectory $folder
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $null = Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings
}
Start-ScheduledTask -TaskName $name
"""
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env={**os.environ, "VK_HARDWARE_FOLDER": str(folder), "VK_HARDWARE_PYTHONW": str(pythonw)},
                   check=True)


def install(folder, grafana):
    garantir_docker()
    services = ["prometheus", "hardware-exporter"]
    if grafana:
        services.append("grafana")
    label = "label=com.docker.compose.project=llm-observabilidade"
    installed = docker("ps", "-a", "--filter", label,
                       "--format", '{{.Label "com.docker.compose.project.working_dir"}}',
                       capture_output=True, check=True).stdout.splitlines()
    if any(Path(path).resolve() != folder for path in installed):
        running = docker("ps", "--filter", label, "--format", '{{.Label "com.docker.compose.service"}}',
                         capture_output=True, check=True).stdout.splitlines()
        if not set(services).issubset(running):
            raise RuntimeError("Já existe um Compose de observabilidade em outra pasta. Use a instalação existente.")
        print("Reutilizando os serviços de observabilidade existentes.")
        return
    if docker("network", "inspect", "llm-local-moe_default", capture_output=True).returncode:
        docker("network", "create", "llm-local-moe_default", check=True)
    (folder / "hardware").mkdir(exist_ok=True)
    if grafana:
        secret = folder / "grafana-admin-password"
        if not secret.exists():
            with secret.open("x", encoding="ascii") as stream:
                stream.write(secrets.token_hex(32))
    docker("compose", "-f", str(folder / "compose.prometheus.yaml"),
           "up", "-d", *services, check=True)
    start_collector(folder)
    meminfo = docker("exec", "llm-local-moe-llama-server-1", "cat", "/proc/meminfo",
                     capture_output=True)
    if meminfo.returncode or not all(key in meminfo.stdout for key in
                                     ("MemAvailable:", "MemTotal:", "SwapTotal:", "SwapFree:")):
        print("Memória WSL indisponível. Inicie o servidor de inferência e confira a coleta no Grafana.",
              file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana", action="store_true", help="Inclui o Grafana além do Prometheus")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    try:
        install(folder, args.grafana)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Falha na observabilidade: {exc}\n")
    if args.grafana:
        (folder / "grafana-habilitado").touch()


if __name__ == "__main__":
    main()
