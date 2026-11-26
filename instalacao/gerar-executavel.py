"""Gera AgenteLocal.exe na pasta de instalação do agente."""

import argparse
from pathlib import Path
import sys

from pip._vendor.distlib.scripts import ScriptMaker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", type=Path, help="Pasta do lançador iniciar_mellum.py.")
    parser.add_argument("--projeto", type=Path, default=Path(__file__).resolve().parent,
                        help="Projeto aberto por duplo clique.")
    parser.add_argument("--grafana", action="store_true", help="Gera também AgenteLocalGrafana.exe.")
    args = parser.parse_args()
    destino = args.destino.resolve(strict=True)
    projeto = args.projeto.resolve(strict=True)
    if not projeto.is_dir() or not (destino / "iniciar_mellum.py").is_file():
        parser.error("Verifique a pasta do projeto e a instalação de iniciar_mellum.py.")
    maker = ScriptMaker(None, str(destino))
    maker.executable = sys.executable
    maker.clobber = True
    maker.variants = {""}
    maker.script_template = (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(sys.argv[0]).resolve().parent))\n"
        "from %(module)s import %(import_name)s\n"
        f"raise SystemExit(%(func)s({ascii(str(projeto)).replace('%', '%%')}))\n"
    )
    entradas = ["AgenteLocal = iniciar_mellum:abrir_executavel",
                "OpenHands = iniciar_openhands:abrir_executavel"]
    if args.grafana:
        entradas.append("AgenteLocalGrafana = iniciar_mellum:abrir_executavel_grafana")
    for caminho in maker.make_multiple(entradas):
        print(caminho)


if __name__ == "__main__":
    main()
