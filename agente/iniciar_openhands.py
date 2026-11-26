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


def docker(*args, check=True):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check)


def start(project, profile):
    project = project.resolve(strict=True)
    if not project.is_dir() or profile not in MODELOS:
        raise ValueError('Projeto ou perfil inválido.')
    config = json.loads((PASTA / 'instalacao.json').read_text(encoding='utf-8'))
    if profile not in config.get('perfis', []):
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
    config = json.loads((PASTA / 'instalacao.json').read_text(encoding='utf-8'))
    profiles = [p for p in ('cobaia', 'base', 'apex') if p in config.get('perfis', [])]
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
        messagebox.showinfo('Configuração do modelo',
                            'Em Settings > LLM > Advanced, configure:\n\n'
                            f'Modelo: openai/{alias}\nBase URL: {API_URL}\n'
                            'API key: local\n\nSelecione /projects como workspace. '
                            'Ao trocar de perfil, configure uma nova conversa.', parent=root)
        webbrowser.open_new_tab(URL)
        root.destroy()

    ttk.Button(frame, text='Escolher projeto e iniciar', command=launch).grid(pady=8)
    root.mainloop()
    return 0
