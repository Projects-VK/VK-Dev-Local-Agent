"""Instala o lançador do agente em uma pasta escolhida no Windows."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


SOURCE = Path(__file__).resolve().parent
FILES = (
    "iniciar_mellum.py", "roteador_local.py", "caminhos_locais.py", "baixar-modelos.py",
    "metodo-de-trabalho.md", "revisao-independente.md", "compose.mellum-base.yaml",
    "compose.mellum-cobaia.yaml", "compose.apex.yaml", "compose.modelos-local.yaml",
    "abrir_grafana.py",
)
OBSERVABILITY = ("instalar-observabilidade.py", "compose.prometheus.yaml", "prometheus.yml",
                 "exportar_hardware.py", "painel_desempenho.py")
MODELS = {
    "mellum": ("Mellum 12B", ("cobaia", "base"), "8,1 GB de pesos. Perfil mais leve, testado com GPU de 8 GiB."),
    "apex": ("Apex 35B", ("apex",), "16,8 GB de pesos. Usa mais RAM; teste local com GPU de 8 GiB e WSL de 14 GiB."),
}
REQUIREMENTS = (
    "Obrigatório: Docker Desktop com Docker Compose. A inferência usa WSL 2 e GPU NVIDIA com CUDA. "
    "Os perfis usam contexto de 32.768 tokens e meta de 768 MiB de VRAM livre no carregamento. "
    "Os números abaixo são referências dos testes, não requisitos mínimos garantidos. "
    "O download e a montagem dos arquivos podem exigir cerca do dobro do espaço de cada modelo."
)


def require_docker():
    docker = shutil.which("docker")
    if not docker:
        raise ValueError("Docker não encontrado. Instale Docker Desktop com Docker Compose e tente novamente.")
    try:
        result = subprocess.run([docker, "compose", "version", "--short"], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Não foi possível verificar o Docker Compose. Confira o Docker Desktop e tente novamente.") from exc
    if result.returncode or not result.stdout.strip():
        raise ValueError("Docker Compose não está disponível. Instale ou atualize o Docker Desktop e tente novamente.")


def choose_installation():
    from tkinter import BooleanVar, Tk, filedialog, messagebox, ttk

    root = Tk()
    root.title("Instalar Agente Local")
    body = ttk.Frame(root, padding=18)
    body.grid()
    ttk.Label(body, text=REQUIREMENTS, wraplength=510).grid(sticky="w", pady=(0, 12))
    choices = {}
    for name, (title, _, details) in MODELS.items():
        choices[name] = BooleanVar(value=name == "mellum")
        ttk.Checkbutton(body, text=title, variable=choices[name]).grid(sticky="w")
        ttk.Label(body, text=details, wraplength=490).grid(sticky="w", padx=20, pady=(0, 8))
    download = BooleanVar(value=True)
    ttk.Checkbutton(body, text="Baixar os modelos selecionados agora", variable=download).grid(sticky="w")
    prometheus = BooleanVar()
    grafana = BooleanVar()

    def update_prometheus():
        if not prometheus.get():
            grafana.set(False)

    def update_grafana():
        if grafana.get():
            prometheus.set(True)

    ttk.Checkbutton(body, text="Instalar monitoramento com Prometheus", variable=prometheus,
                    command=update_prometheus).grid(sticky="w")
    ttk.Checkbutton(body, text="Instalar painel Grafana", variable=grafana,
                    command=update_grafana).grid(sticky="w")
    result = None

    def accept():
        nonlocal result
        models = tuple(name for name, variable in choices.items() if variable.get())
        if not models:
            messagebox.showerror("Seleção de modelos", "Selecione pelo menos um modelo.", parent=root)
            return
        parent = filedialog.askdirectory(parent=root, initialdir=str(Path.home()),
                                         title="Escolha onde criar a pasta AgenteLocal", mustexist=True)
        if parent:
            result = Path(parent) / "AgenteLocal", models, download.get(), prometheus.get(), grafana.get()
            root.destroy()

    ttk.Button(body, text="Escolher pasta e instalar", command=accept).grid(sticky="e", pady=(14, 0))
    root.mainloop()
    return result


def install(destination, data, models, prometheus=False, grafana=False):
    if destination.exists():
        raise ValueError(f"A pasta de instalação já existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".agente-local-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "instalacao"
        staged.mkdir()
        for name in FILES:
            shutil.copy2(SOURCE / name, staged / name)
        if prometheus:
            for name in OBSERVABILITY:
                shutil.copy2(SOURCE / name, staged / name)
        if grafana:
            shutil.copytree(SOURCE / "grafana", staged / "grafana")
        profiles = [profile for name in models for profile in MODELS[name][1]]
        (staged / "instalacao.json").write_text(json.dumps({"dados": str(data), "perfis": profiles}, indent=2) + "\n",
                                                encoding="utf-8")
        command = [sys.executable, "-B", str(SOURCE / "gerar-executavel.py"),
                   str(staged), "--projeto", str(destination.parent)]
        if grafana:
            command.append("--grafana")
        subprocess.run(command, check=True)
        if not (staged / "AgenteLocal.exe").is_file():
            raise RuntimeError("O gerador não produziu AgenteLocal.exe.")
        if grafana and not (staged / "AgenteLocalGrafana.exe").is_file():
            raise RuntimeError("O gerador não produziu AgenteLocalGrafana.exe.")
        models = data / "modelos"
        if models.is_relative_to(destination):
            (staged / models.relative_to(destination)).mkdir(parents=True, exist_ok=True)
        else:
            models.mkdir(parents=True, exist_ok=True)
        staged.rename(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, help="Nova pasta de instalação")
    parser.add_argument("--dados", type=Path, help="Pasta de dados. O padrão é <instalação>/dados")
    parser.add_argument("--modelos", nargs="+", choices=MODELS, default=["mellum"],
                        help="Modelos da instalação por linha de comando. Padrão: mellum")
    parser.add_argument("--sem-download", action="store_true", help="Prepara a instalação sem baixar os pesos agora")
    parser.add_argument("--prometheus", action="store_true", help="Instala o monitoramento")
    parser.add_argument("--grafana", action="store_true", help="Instala o painel e o Prometheus")
    args = parser.parse_args()
    try:
        require_docker()
    except ValueError as exc:
        if args.destino is None:
            from tkinter import Tk, messagebox

            root = Tk()
            root.withdraw()
            messagebox.showerror("Requisito de instalação", str(exc), parent=root)
            root.destroy()
        parser.exit(1, f"{exc}\n")
    if args.destino:
        destination, models, download = args.destino, tuple(dict.fromkeys(args.modelos)), not args.sem_download
        prometheus, grafana = args.prometheus or args.grafana, args.grafana
        print(REQUIREMENTS, flush=True)
        for name in models:
            print(f"{MODELS[name][0]} — {MODELS[name][2]}", flush=True)
    else:
        selection = choose_installation()
        if selection is None:
            return
        destination, models, download, prometheus, grafana = selection
    destination = destination.resolve()
    data = (args.dados or destination / "dados").resolve()
    try:
        install(destination, data, models, prometheus, grafana)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Falha na instalação: {exc}\n")
    print(f"Lançador: {destination / 'AgenteLocal.exe'}")
    print(f"Modelos: {data / 'modelos'}")
    if download:
        try:
            subprocess.run([sys.executable, "-B", str(destination / "baixar-modelos.py"), *models], check=True)
        except subprocess.CalledProcessError:
            parser.exit(1, "O lançador foi instalado. Para retomar os downloads, execute baixar-modelos.py "
                           f"na pasta de instalação com: {' '.join(models)}.\n")
    if prometheus:
        command = [sys.executable, "-B", str(destination / "instalar-observabilidade.py")]
        if grafana:
            command.append("--grafana")
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            extra = " --grafana" if grafana else ""
            parser.exit(1, "O agente está instalado. Para retomar a observabilidade, execute "
                           f"python -B instalar-observabilidade.py{extra} na pasta de instalação.\n")


if __name__ == "__main__":
    main()
