"""Painel local da sessão Claude Code e da inferência."""

import argparse
import json
from queue import Empty, Queue
import re
import subprocess
from threading import Event, Thread
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener


HTTP = build_opener(ProxyHandler({}))
URL = "http://127.0.0.1:11435"
CONTAINER = "llm-local-moe-llama-server-1"
GIB = 1024 ** 3
MIB = 1024 ** 2


def ler(comando):
    try:
        return subprocess.check_output(comando, encoding="utf-8", errors="replace",
                                       timeout=4, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def api(path):
    with HTTP.open(URL + path, timeout=2) as response:
        return json.load(response)


def colher_hardware():
    dados = {}
    linha = ler(["nvidia-smi", "--query-gpu=memory.free,memory.total,utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"]).splitlines()
    if linha:
        try:
            livre, total, uso, temperatura = linha[0].split(",")
            dados["gpu"] = (int(livre), int(total), int(uso), float(temperatura))
        except ValueError:
            pass

    cgroup = ler(["docker", "exec", CONTAINER, "cat", "/sys/fs/cgroup/memory.current",
                  "/sys/fs/cgroup/memory.stat", "/sys/fs/cgroup/memory.swap.current",
                  "/sys/fs/cgroup/cpu.stat"])
    if cgroup:
        linhas = cgroup.splitlines()
        campos = {k: int(v) for k, v in re.findall(r"^(\w+) (\d+)$", cgroup, re.M)}
        numericas = [int(linha) for linha in linhas if linha.isdigit()]
        if len(numericas) == 2 and campos.keys() >= {"anon", "file", "usage_usec"}:
            dados["container"] = (numericas[0], campos["anon"], campos["file"],
                                  numericas[1], campos["usage_usec"])

    meminfo = ler(["docker", "exec", CONTAINER, "cat", "/proc/meminfo"])
    ubuntu = {k: int(v) * 1024 for k, v in re.findall(r"^(\w+):\s+(\d+) kB", meminfo, re.M)}
    if ubuntu.keys() >= {"MemAvailable", "MemTotal", "SwapTotal", "SwapFree"}:
        dados["ubuntu"] = (ubuntu["MemAvailable"], ubuntu["MemTotal"],
                           ubuntu["SwapTotal"] - ubuntu["SwapFree"])

    return dados


def colher(pid):
    dados = colher_hardware()
    processo = ler(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    f"Get-Process -Id {pid} | Select-Object WorkingSet64,CPU | ConvertTo-Json -Compress"])
    if processo:
        p = json.loads(processo)
        dados["claude"] = (p["WorkingSet64"], p["CPU"])
    try:
        modelo = api("/v1/models")["data"][0]["id"]
        slots = api("/slots")
        dados["modelo"] = modelo
        dados["estado"] = "Gerando" if any(slot["is_processing"] for slot in slots) else "Disponível"
    except HTTPError as erro:
        dados["estado"] = "Carregando modelo" if erro.code == 503 else "API indisponível"
    except (OSError, ValueError, KeyError, IndexError):
        dados["estado"] = "API indisponível"
    dados["timestamp"] = time.monotonic()
    return dados


def apresentar(dados, anterior):
    def cpu(chave, indice, divisor=1):
        if chave in anterior:
            dt = dados["timestamp"] - anterior["timestamp"]
            delta = dados[chave][indice] - anterior[chave][indice]
            if dt > 0 and delta >= 0 and (chave != "container" or dados.get("modelo") == anterior.get("modelo")):
                return f"{delta / dt / divisor:.2f} núcleos"
        return "calculando CPU"

    linhas = {}
    if "claude" in dados:
        linhas["Claude Code"] = f"{dados['claude'][0] / MIB:.0f} MiB de RAM  ·  {cpu('claude', 1)}"
    if "gpu" in dados:
        livre, total, uso, temp = dados["gpu"]
        linhas["GPU NVIDIA"] = f"{livre} / {total} MiB livres  ·  {uso}% de uso  ·  {temp:.0f} °C"
    if "container" in dados:
        total, anon, cache, swap, _ = dados["container"]
        linhas["Contêiner"] = (f"{total / GIB:.2f} GiB de RAM  ·  {cpu('container', 4, 1e6)}\n"
                               f"{anon / GIB:.2f} GiB anônima  ·  {cache / GIB:.2f} GiB arquivos  ·  {swap / GIB:.2f} GiB swap")
    if "ubuntu" in dados:
        livre, total, swap = dados["ubuntu"]
        linhas["Ubuntu · WSL"] = f"{livre / GIB:.2f} / {total / GIB:.2f} GiB disponíveis  ·  {swap / GIB:.2f} GiB swap"
    return linhas


def janela(pid):
    import tkinter as tk

    root = tk.Tk()
    root.title("Desempenho local")
    root.configure(bg="#111827")
    root.geometry("530x370")
    root.minsize(480, 350)
    fonte = "Segoe UI"

    def label(texto, tamanho, cor, peso="normal"):
        return tk.Label(root, text=texto, font=(fonte, tamanho, peso), bg="#111827",
                        fg=cor, anchor="w", justify="left")

    titulo = label("Servidor local", 17, "#F3F4F6", "bold")
    titulo.pack(fill="x", padx=20, pady=(15, 0))
    status = label("Coletando métricas…", 10, "#93C5FD")
    status.pack(fill="x", padx=20, pady=(1, 4))
    rotulos = {}
    for nome in ("Claude Code", "GPU NVIDIA", "Contêiner", "Ubuntu · WSL"):
        label(nome, 10, "#9CA3AF", "bold").pack(fill="x", padx=20, pady=(9, 0))
        rotulos[nome] = label("Aguardando leitura…", 11, "#F3F4F6")
        rotulos[nome].pack(fill="x", padx=20)
    rodape = label("", 9, "#9CA3AF")
    rodape.pack(side="bottom", fill="x", padx=20, pady=12)

    fila = Queue(maxsize=1)
    parar = Event()

    def coletar():
        while not parar.is_set():
            dados = colher(pid)
            try:
                fila.get_nowait()
            except Empty:
                pass
            fila.put(dados)
            parar.wait(3)

    anterior = {}

    def atualizar():
        nonlocal anterior
        try:
            dados = fila.get_nowait()
        except Empty:
            pass
        else:
            modelo = dados.get("modelo", "")
            nome = {"apex-35b-v1": "Apex 35B", "mellum2.1-12b-a2.5b-cobaia": "Mellum cobaia",
                    "mellum2.1-12b-a2.5b": "Mellum base"}.get(modelo, modelo)
            titulo.config(text=nome or "Servidor local")
            status.config(text=dados["estado"])
            linhas = apresentar(dados, anterior)
            for chave, rotulo in rotulos.items():
                rotulo.config(text=linhas.get(chave, "Leitura indisponível"))
            rotulos["GPU NVIDIA"].config(fg="#FBBF24" if dados.get("gpu", (768,))[0] < 768 else "#F3F4F6")
            rodape.config(text=f"Atualizado às {time.strftime('%H:%M:%S')}  ·  GPU total do dispositivo")
            anterior = dados
        root.after(250, atualizar)

    Thread(target=coletar, daemon=True).start()
    root.after(100, atualizar)
    try:
        root.mainloop()
    finally:
        parar.set()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("--amostra", action="store_true", help="Lê os contadores sem abrir janela.")
    args = parser.parse_args()
    if args.amostra:
        print(json.dumps(colher(args.pid)))
    else:
        janela(args.pid)
