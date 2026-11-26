"""Inicia o OpenHands local com um perfil de modelo por sessão."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import webbrowser
from urllib.request import urlopen

from iniciar_mellum import MODELOS, PASTA, carregar, garantir_docker
from roteador_local import trava_modelo

IMAGE = 'ghcr.io/openhands/agent-canvas@sha256:3d805efd6bfefb006e86a1390b5b015094320d7b8820423050047c8f6b472f9d'
NETWORK = 'llm-local-moe_default'
URL = 'http://127.0.0.1:18081/canvas'
API_URL = 'http://llama-server:8080/v1'


def installed_profiles():
    config = PASTA / 'instalacao.json'
    if not config.exists():
        # Instalações anteriores usam os perfis e o volume Docker originais.
        return list(MODELOS)
    value = json.loads(config.read_text(encoding='utf-8'))
    return value.get('perfis', [])


def docker(*args, check=True):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check)


def iniciar_monitoramento():
    """Inicia apenas os serviços de observabilidade já configurados."""
    grafana = (PASTA / 'grafana-habilitado').is_file()
    compose = PASTA / 'compose.prometheus.yaml'
    if not grafana and not compose.is_file():
        return
    wanted = {'prometheus', 'hardware-exporter'}
    if grafana:
        wanted.add('grafana')
    result = docker('ps', '-a', '--filter', 'label=com.docker.compose.project=llm-observabilidade',
                    '--format', '{{.ID}}\t{{.Label "com.docker.compose.service"}}\t{{.State}}')
    found = set()
    for line in result.stdout.splitlines():
        fields = line.split('\t')
        if len(fields) != 3 or fields[1] not in wanted:
            continue
        found.add(fields[1])
        if fields[2] != 'running':
            docker('start', fields[0])
    missing = wanted - found
    if missing:
        if not compose.is_file():
            raise RuntimeError('Serviços de monitoramento ausentes: ' + ', '.join(sorted(missing)))
        docker('compose', '-f', str(compose), 'up', '-d', *sorted(missing))


def start(project, profile):
    project = project.resolve(strict=True)
    if not project.is_dir() or profile not in MODELOS:
        raise ValueError('Projeto ou perfil inválido.')
    if profile not in installed_profiles():
        raise ValueError('O perfil não foi selecionado nesta instalação.')
    garantir_docker()
    ident = hashlib.sha256(str(PASTA.resolve()).lower().encode('utf-8')).hexdigest()[:12]
    name = 'vk-openhands-' + ident
    volume = name + '-dados'
    with trava_modelo(PASTA / 'roteador.lock'):
        carregar(profile)
    if docker('image', 'inspect', IMAGE, check=False).returncode:
        subprocess.run(['docker', 'pull', IMAGE], check=True)
    inspected = docker('inspect', name, check=False)
    if inspected.returncode == 0:
        info = json.loads(inspected.stdout)[0]
        labels = info['Config'].get('Labels') or {}
        mounts = info.get('Mounts', [])
        if labels.get('vk.installation') != ident or not any(
                x.get('Destination') == '/projects' and Path(x.get('Source', '')).resolve() == project
                for x in mounts):
            raise ValueError('Já existe um contêiner OpenHands com outra pasta de projeto. Preserve e encerre essa instalação antes de mudar de pasta.')
        if NETWORK not in info['NetworkSettings']['Networks']:
            docker('network', 'connect', NETWORK, name)
        if not info['State']['Running']:
            docker('start', name)
    else:
        docker('run', '-d', '--name', name, '--label', 'vk.installation=' + ident,
               '--network', NETWORK, '-p', '127.0.0.1:18081:8000',
               '-e', 'AGENT_CANVAS_DISABLE_TELEMETRY=1',
               '-e', 'AGENT_CANVAS_ALLOW_LAN_SESSION_KEY=true',
               '--mount', f'type=volume,source={volume},target=/home/openhands/.openhands',
               '--mount', f'type=bind,source={project},target=/projects', IMAGE)
    for _ in range(90):
        try:
            with urlopen(URL, timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError('OpenHands não ficou disponível em 90 segundos. Verifique os logs do contêiner.')
    return MODELOS[profile]


def abrir_executavel(projeto_padrao):
    from tkinter import Tk, StringVar, filedialog, messagebox, ttk
    root = Tk()
    root.title('Agente Local - OpenHands')
    frame = ttk.Frame(root, padding=16)
    frame.grid()
    profiles = [p for p in ('cobaia', 'base', 'apex') if p in installed_profiles()]
    if not profiles:
        messagebox.showerror('OpenHands', 'Nenhum modelo configurado.', parent=root)
        root.destroy()
        return 1
    selected = StringVar(value=profiles[0])
    ttk.Label(frame, text='Modelo para esta sessão:').grid(sticky='w')
    ttk.Combobox(frame, textvariable=selected, values=profiles, state='readonly').grid(sticky='ew')
    ttk.Label(frame, text='A pasta escolhida será acessível ao agente com escrita.', wraplength=400).grid(pady=8)

    def launch():
        project = filedialog.askdirectory(parent=root, title='Escolha a pasta do projeto',
                                          initialdir=str(projeto_padrao), mustexist=True)
        if not project:
            return
        try:
            alias = start(Path(project), selected.get())
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            messagebox.showerror('Falha ao iniciar OpenHands', str(exc), parent=root)
            return
        try:
            iniciar_monitoramento()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            messagebox.showwarning('Monitoramento indisponível',
                                   'OpenHands iniciou, mas não foi possível iniciar o monitoramento: ' + str(exc),
                                   parent=root)
        messagebox.showinfo('Configuração do modelo',
                            'Em Settings > LLM > Advanced, digite apenas os valores abaixo, sem os nomes dos campos:\n\n'
                            f'Modelo:\nopenai/{alias}\n\nBase URL:\n{API_URL}\n\n'
                            'API key:\nlocal\n\nSelecione /projects como workspace. '
                            'Ao trocar de perfil, configure uma nova conversa.', parent=root)
        webbrowser.open_new_tab(URL)
        if (PASTA / 'grafana-habilitado').is_file():
            from abrir_grafana import abrir
            abrir()
        root.destroy()

    ttk.Button(frame, text='Escolher projeto e iniciar', command=launch).grid(pady=8)
    root.mainloop()
    return 0
