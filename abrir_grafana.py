"""Abre o dashboard local quando o Grafana está disponível."""

from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser


def abrir():
    url = "http://127.0.0.1:3000"
    http = build_opener(ProxyHandler({}))
    try:
        with http.open(f"{url}/api/health", timeout=2):
            pass
        webbrowser.open_new_tab(f"{url}/d/llm-inferencia/inferencia-local")
    except (URLError, OSError, webbrowser.Error):
        return
