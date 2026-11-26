"""Remove arquivos de uma instalação do Agente Local com confirmação."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

MODEL_FILES = {'base': 'Mellum2.1-12B-A2.5B-Thinking-Q4_K_M.gguf',
               'cobaia': 'Mellum2.1-12B-A2.5B-Thinking-Q4_K_M.gguf',
               'apex': 'Apex-35B-V1.0-IQ3_XS.gguf'}


def remove_containers(folder):
    docker = shutil.which('docker')
    if not docker:
        raise RuntimeError('Docker não encontrado; os contêineres foram preservados.')
    query = subprocess.run([docker, 'ps', '-a', '--format',
                            '{{.ID}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.project.working_dir"}}'],
                           capture_output=True, text=True, check=True)
    ids = []
    for line in query.stdout.splitlines():
        fields = line.split('\t')
        if len(fields) == 3 and fields[1] in ('llm-local-moe', 'llm-observabilidade') and fields[2]:
            if Path(fields[2]).resolve() == folder.resolve():
                ids.append(fields[0])
    if ids:
        subprocess.run([docker, 'rm', '-f', *ids], check=True)
    return len(ids)


def uninstall(folder, delete_models=False, containers=False):
    folder = folder.resolve(strict=True)
    config = folder / 'instalacao.json'
    manifest_file = folder / 'arquivos-instalados.json'
    if not config.is_file() or not manifest_file.is_file():
        raise ValueError('Instalação sem manifesto reconhecido. Nenhum arquivo foi removido; instalações anteriores exigem remoção manual.')
    config_data = json.loads(config.read_text(encoding='utf-8'))
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(config_data.get('dados'), str):
        raise ValueError('Manifesto ou configuração inválidos.')
    files = []
    for name, digest in manifest.items():
        candidate = folder / name
        if not isinstance(name, str) or not isinstance(digest, str) or candidate.is_symlink():
            raise ValueError('Entrada inválida no manifesto.')
        resolved = candidate.resolve()
        if not resolved.is_relative_to(folder) or resolved == folder:
            raise ValueError('Manifesto contém caminho fora da instalação.')
        files.append((candidate, digest))
    count = remove_containers(folder) if containers else 0
    preserved = []
    if delete_models:
        models = Path(config_data['dados']) / 'modelos'
        for name in {MODEL_FILES[p] for p in config_data.get('perfis', []) if p in MODEL_FILES}:
            p = models / name
            if p.is_symlink():
                preserved.append(str(p))
            elif p.is_file():
                p.unlink()
    for path, digest in files:
        if path.is_file():
            if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                path.unlink()
            else:
                preserved.append(str(path))
    manifest_file.unlink()
    for directory in sorted((p for p in folder.rglob('*') if p.is_dir() and not p.is_symlink()), key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    try:
        folder.rmdir()
    except OSError:
        preserved.append(str(folder))
    return count, preserved


def main():
    from tkinter import BooleanVar, Tk, messagebox, ttk
    folder = Path(__file__).resolve().parent
    root = Tk()
    root.title('Desinstalar Agente Local')
    frame = ttk.Frame(root, padding=18)
    frame.grid()
    ttk.Label(frame, text=f'Instalação: {folder}\nArquivos alterados e dados não reconhecidos serão preservados.', wraplength=520).grid(sticky='w')
    models = BooleanVar(value=False)
    containers = BooleanVar(value=False)
    ttk.Checkbutton(frame, text='Excluir os arquivos dos modelos Mellum e Apex', variable=models).grid(sticky='w', pady=5)
    ttk.Checkbutton(frame, text='Remover contêineres vinculados a esta pasta', variable=containers).grid(sticky='w', pady=5)
    ttk.Label(frame, text='Volumes, imagens, tarefa do coletor, Docker, WSL, Python e Claude Code são preservados.', wraplength=520).grid(sticky='w', pady=5)

    def confirm():
        if not messagebox.askyesno('Confirmar desinstalação', 'Remover os itens selecionados? Esta ação não pode ser desfeita.', parent=root):
            return
        try:
            count, preserved = uninstall(folder, models.get(), containers.get())
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            messagebox.showerror('Desinstalação interrompida', str(exc), parent=root)
            return
        messagebox.showinfo('Desinstalação concluída', f'Contêineres removidos: {count}.\nItens preservados: {len(preserved)}.\n' + '\n'.join(preserved[:10]), parent=root)
        root.destroy()

    ttk.Button(frame, text='Desinstalar', command=confirm).grid(sticky='e', pady=(10, 0))
    root.mainloop()


if __name__ == '__main__':
    main()
