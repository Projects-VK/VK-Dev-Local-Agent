"""Caminhos persistidos por uma instalação do agente."""

import json
from pathlib import Path


def ler_instalacao(pasta):
    arquivo = pasta / "instalacao.json"
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.is_file() else {}


def modelos_instalados(pasta):
    dados = ler_instalacao(pasta).get("dados")
    return Path(dados) / "modelos" if dados else None
