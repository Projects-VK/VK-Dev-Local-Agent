"""Abre o Claude Code local na pasta escolhida com o perfil de trabalho do Mellum."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


PASTA = Path(__file__).resolve().parent
URL = "http://127.0.0.1:11435"
MODELOS = {"base": "mellum2.1-12b-a2.5b", "cobaia": "mellum2.1-12b-a2.5b-cobaia", "apex": "apex-35b-v1"}
HTTP = build_opener(ProxyHandler({}))


def consultar(recurso):
    with HTTP.open(URL + recurso, timeout=5) as resposta:
        return json.load(resposta)


def modelo_ativo():
    return consultar("/v1/models")["data"][0]["id"]


def perfil_residente():
    prazo = time.monotonic() + 120
    while time.monotonic() < prazo:
        try:
            modelo = modelo_ativo()
        except HTTPError as erro:
            if erro.code != 503:
                raise
        except URLError as erro:
            if isinstance(erro.reason, ConnectionRefusedError):
                return None
            raise
        except (ConnectionError, TimeoutError):
            pass
        else:
            for perfil, alias in MODELOS.items():
                if alias == modelo:
                    return perfil
            raise ValueError(f"O modelo ativo não tem perfil no lançador: {modelo}.")
        time.sleep(2)
    raise ValueError("O servidor ainda está carregando após 120 s.")


def carregar(perfil, *, silencioso=False):
    prazo = time.monotonic() + 120
    while True:
        try:
            if modelo_ativo() == MODELOS[perfil]:
                return
            if any(slot["is_processing"] for slot in consultar("/slots")):
                raise ValueError("Há uma geração em andamento. Tente carregar o perfil depois.")
            break
        except HTTPError as erro:
            if erro.code != 503:
                raise
        except URLError as erro:
            if isinstance(erro.reason, ConnectionRefusedError):
                break
            raise
        except (ConnectionError, TimeoutError):
            pass
        if time.monotonic() >= prazo:
            raise ValueError("O servidor local continua em inicialização após 120 s.")
        time.sleep(2)
    compose = ["docker", "compose", "-f", str(PASTA / "compose.mellum-base.yaml")]
    if perfil == "cobaia":
        compose += ["-f", str(PASTA / "compose.mellum-cobaia.yaml")]
    elif perfil == "apex":
        compose += ["-f", str(PASTA / "compose.apex.yaml")]
    env = {**os.environ, "LLM_CTX_SIZE": "32768"}
    if (PASTA / "instalacao.json").is_file():
        from caminhos_locais import modelos_instalados

        compose += ["-f", str(PASTA / "compose.modelos-local.yaml")]
        env["LLM_MODELOS_DIR"] = str(modelos_instalados(PASTA))
        rede = ["docker", "network", "inspect", "llm-local-moe_default"]
        if subprocess.run(rede, capture_output=True).returncode:
            subprocess.run(["docker", "network", "create", "llm-local-moe_default"], check=True)
    subprocess.run(compose + ["up", "-d", "--pull", "never"], check=True, capture_output=silencioso,
                   env=env)
    prazo = time.monotonic() + 120
    while time.monotonic() < prazo:
        try:
            if consultar("/health").get("status") == "ok" and modelo_ativo() == MODELOS[perfil]:
                return
        except (URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(2)
    raise ValueError(f"O servidor não ficou pronto com o modelo {MODELOS[perfil]} em 120 s.")


def comando_claude(cli: Path, perfil: str, projeto: Path, *, mcp: Path | None = None,
                   revisao=False, roteado=False):
    if not projeto.is_dir():
        raise ValueError(f"Pasta de trabalho inexistente: {projeto}")
    if revisao and (perfil != "cobaia" or mcp):
        raise ValueError("A revisão independente usa a cobaia e as ferramentas locais de leitura.")
    modelo = MODELOS[perfil]
    contexto = 32768
    if not roteado:
        ativo = modelo_ativo()
        if ativo != modelo:
            raise ValueError(f"Modelo ativo: {ativo}. Use --carregar para selecionar {modelo}.")
        contexto = int(consultar("/props")["default_generation_settings"]["n_ctx"])
    if contexto < 1:
        raise ValueError("O servidor retornou um tamanho de contexto inválido.")
    env = os.environ.copy()
    for chave in ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                  "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_USE_ANTHROPIC_AWS"):
        env.pop(chave, None)
    env.update(ANTHROPIC_BASE_URL=URL, ANTHROPIC_API_KEY="local", ANTHROPIC_MODEL=modelo,
               ANTHROPIC_SMALL_FAST_MODEL=modelo, CLAUDE_CODE_SUBAGENT_MODEL=modelo,
               CLAUDE_CODE_MAX_CONTEXT_TOKENS=str(contexto), CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
               ENABLE_CLAUDEAI_MCP_SERVERS="false", NO_PROXY="127.0.0.1,localhost,::1")
    for nivel in ("OPUS", "SONNET", "HAIKU"):
        env[f"ANTHROPIC_DEFAULT_{nivel}_MODEL"] = modelo
    comando = [str(cli.resolve(strict=True)), "--bare", "--strict-mcp-config", "--model", modelo]
    if roteado or perfil in ("cobaia", "apex"):
        instrucao = "revisao-independente.md" if revisao else "metodo-de-trabalho.md"
        comando += ["--append-system-prompt-file", str((PASTA / instrucao).resolve(strict=True))]
    if revisao:
        comando += ["--tools", "Read,Glob,Grep"]
    if mcp:
        comando += ["--mcp-config", str(mcp.resolve(strict=True))]
    return comando, env


def localizar_claude():
    extensao = (Path.home() / ".vscode/extensions/anthropic.claude-code-2.1.216-win32-x64"
                / "resources/native-binary/claude.exe")
    for caminho in (extensao, shutil.which("claude"), Path.home() / ".local/bin/claude.exe"):
        if caminho and Path(caminho).is_file():
            return Path(caminho)
    raise ValueError("Informe o executável do Claude Code com --claude.")


def garantir_docker():
    docker = shutil.which("docker")
    if not docker:
        raise ValueError("O Docker Desktop precisa estar instalado para carregar o Mellum.")
    try:
        ativo = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"], cwd=PASTA,
                               capture_output=True, timeout=10).returncode == 0
    except subprocess.TimeoutExpired:
        ativo = False
    if not ativo:
        print("Iniciando o Docker Desktop...", flush=True)
        subprocess.run([docker, "desktop", "start", "--timeout", "120"], cwd=PASTA, check=True)


def abrir_claude(comando, env, projeto, mostrar_painel):
    with subprocess.Popen(comando + ["--permission-mode", "manual"], cwd=projeto, env=env) as cliente:
        if mostrar_painel:
            from abrir_grafana import abrir

            abrir()
        return cliente.wait()


def main(argumentos=None, *, projeto_padrao=None, com_grafana=False):
    perfis = MODELOS
    if (PASTA / "instalacao.json").is_file():
        from caminhos_locais import ler_instalacao

        selecionados = ler_instalacao(PASTA).get("perfis", MODELOS)
        perfis = {perfil: alias for perfil, alias in MODELOS.items() if perfil in selecionados}
    if not perfis:
        print("Nenhum perfil de modelo configurado na instalação.", file=sys.stderr)
        return 1
    padrao = "cobaia" if "cobaia" in perfis else next(iter(perfis))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projeto", type=Path, default=projeto_padrao or Path.cwd(), help="Pasta de trabalho da sessão.")
    parser.add_argument("--perfil", choices=perfis,
                        help="Escolhe um modelo. O executável reutiliza o modelo ativo quando omitido.")
    parser.add_argument("--carregar", action="store_true", help="Ativa o perfil no contêiner único do projeto.")
    parser.add_argument("--sem-painel", action="store_true", help="Abre a sessão sem abrir o Grafana.")
    parser.add_argument("--orcamento-apex", action="store_true",
                        help="Liga o orçamento experimental de raciocínio do Apex pelo menu de esforço.")
    ferramentas = parser.add_mutually_exclusive_group()
    ferramentas.add_argument("--mcp", type=Path, help="Arquivo de ferramentas MCP escolhido para esta sessão.")
    ferramentas.add_argument("--revisar", action="store_true", help="Abre uma nova sessão de revisão com ferramentas de leitura.")
    parser.add_argument("--claude", type=Path, help="Caminho do executável do Claude Code.")
    args = parser.parse_args(argumentos)
    mostrar_painel = com_grafana and not args.sem_painel and (PASTA / "grafana-habilitado").is_file()
    try:
        projeto = args.projeto.resolve(strict=True)
        if not projeto.is_dir():
            raise ValueError(f"Selecione uma pasta para o projeto: {projeto}")
        cli = args.claude or localizar_claude()
        perfil = args.perfil or padrao
        if args.revisar and perfil != "cobaia":
            parser.error("--revisar faz parte do perfil cobaia.")
        if projeto_padrao is not None and not args.revisar and args.perfil != "base":
            from roteador_local import roteador, trava_modelo

            lock_path = PASTA / "roteador.lock"
            garantir_docker()
            residente = perfil_residente() if args.perfil is None else None
            if residente in perfis:
                perfil = residente
            else:
                with trava_modelo(lock_path):
                    residente = perfil_residente()
                    perfil = args.perfil or (residente if residente in perfis else padrao)
                    carregar(perfil)
            comando, env = comando_claude(cli, perfil, projeto, mcp=args.mcp, roteado=True)
            with roteador(URL, HTTP, perfis, lambda perfil: carregar(perfil, silencioso=True),
                          modelo_ativo, consultar, lock_path,
                          orcamento_apex=args.orcamento_apex) as (url, chave):
                env.update(
                    ANTHROPIC_BASE_URL=url, ANTHROPIC_API_KEY=chave, API_TIMEOUT_MS="2000000",
                    CLAUDE_CODE_DISABLE_1M_CONTEXT="1",
                    CLAUDE_CODE_MAX_CONTEXT_TOKENS="32768",
                    ANTHROPIC_DEFAULT_SONNET_MODEL=perfis.get("cobaia", perfis[perfil]),
                    ANTHROPIC_DEFAULT_SONNET_MODEL_NAME="Mellum" if "cobaia" in perfis else "Apex",
                    ANTHROPIC_DEFAULT_OPUS_MODEL=perfis.get("apex", perfis[perfil]),
                    ANTHROPIC_DEFAULT_OPUS_MODEL_NAME="Apex" if "apex" in perfis else "Mellum",
                )
                if "base" in perfis:
                    env.update(ANTHROPIC_CUSTOM_MODEL_OPTION=perfis["base"],
                               ANTHROPIC_CUSTOM_MODEL_OPTION_NAME="Mellum base")
                else:
                    for key in ("ANTHROPIC_CUSTOM_MODEL_OPTION", "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME"):
                        env.pop(key, None)
                print("Use /model para escolher o modelo.", flush=True)
                return abrir_claude(comando, env, projeto, mostrar_painel)
        if args.carregar:
            if projeto_padrao is not None:
                garantir_docker()
            carregar(perfil)
        comando, env = comando_claude(cli, perfil, projeto, mcp=args.mcp, revisao=args.revisar)
        return abrir_claude(comando, env, projeto, mostrar_painel)
    except URLError as erro:
        print(f"Servidor local indisponível em {URL}. Verifique o Docker Desktop e use --carregar. {erro}", file=sys.stderr)
    except (OSError, ValueError, KeyError, IndexError, subprocess.CalledProcessError) as erro:
        print(erro, file=sys.stderr)
    return 1


def abrir_executavel(projeto_padrao, *, com_grafana=False):
    argumentos = sys.argv[1:]
    if not argumentos or argumentos == ["--perfil", "apex"]:
        from tkinter import filedialog

        pasta = filedialog.askdirectory(title="Agente Local - Escolha a pasta do projeto",
                                       initialdir=str(Path(projeto_padrao)), mustexist=True)
        if not pasta:
            return 0
        argumentos = [*argumentos, "--projeto", pasta]
    if argumentos and not argumentos[0].startswith("-"):
        argumentos = ["--projeto", *argumentos]
    codigo = main(["--carregar", *argumentos], projeto_padrao=Path(projeto_padrao), com_grafana=com_grafana)
    if codigo and sys.stdin.isatty():
        input("Pressione Enter para fechar.")
    return codigo


def abrir_executavel_grafana(projeto_padrao):
    return abrir_executavel(projeto_padrao, com_grafana=True)


if __name__ == "__main__":
    raise SystemExit(main())
