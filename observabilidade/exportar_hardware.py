"""Publica métricas do Windows, GPU, WSL e contêiner para o node_exporter."""

import argparse
from pathlib import Path
import time

from painel_desempenho import MIB, colher_hardware, ler


def coletar():
    dados = colher_hardware()
    series = {"llm_hardware_sample_timestamp_seconds": int(time.time())}
    if "gpu" in dados:
        livre, total, _, _ = dados["gpu"]
        series.update(llm_gpu_vram_free_bytes=livre * MIB,
                      llm_gpu_vram_used_bytes=(total - livre) * MIB,
                      llm_gpu_vram_total_bytes=total * MIB)
    if "container" in dados:
        total, anon, cache, swap, _ = dados["container"]
        series.update(llm_container_ram_bytes=total, llm_container_ram_anon_bytes=anon,
                      llm_container_ram_file_bytes=cache, llm_container_swap_used_bytes=swap)
    if "ubuntu" in dados:
        livre, total, swap = dados["ubuntu"]
        series.update(llm_wsl_ram_available_bytes=livre, llm_wsl_ram_total_bytes=total,
                      llm_wsl_swap_used_bytes=swap)
    ram = ler(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
               "[long](Get-Process -Name claude -ErrorAction SilentlyContinue | "
               "Measure-Object -Property WorkingSet64 -Sum).Sum"])
    if ram.isdigit():
        series["llm_claude_ram_working_set_bytes"] = int(ram)
    # OpenHands é opcional; a ausência do contêiner não afeta as demais séries.
    openhands = ler(["docker", "ps", "--filter", "name=vk-openhands-", "--format", "{{.Names}}"])
    if openhands:
        total_openhands = 0
        found = False
        for name in openhands.splitlines():
            if not name.startswith("vk-openhands-"):
                continue
            value = ler(["docker", "exec", name, "cat", "/sys/fs/cgroup/memory.current"])
            if value.isdigit():
                total_openhands += int(value)
                found = True
        if found:
            series["llm_openhands_container_ram_bytes"] = total_openhands
    return series


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", type=Path)
    args = parser.parse_args()
    pending = args.arquivo.with_suffix(".tmp")
    while True:
        series = coletar()
        try:
            payload = "".join(f"# TYPE {name} gauge\n{name} {value}\n" for name, value in series.items())
            pending.write_bytes(payload.encode("ascii"))
            pending.replace(args.arquivo)
        except PermissionError:
            # A próxima coleta tenta novamente se o arquivo estiver aberto.
            pass
        time.sleep(10)


if __name__ == "__main__":
    main()
