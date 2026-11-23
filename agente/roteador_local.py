"""Encaminha solicitações do Claude Code para o único servidor de inferência."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import msvcrt
import secrets
import time
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request


ORCAMENTO_APEX = {"low": 1024, "medium": 2048, "high": 4096, "xhigh": 8192, "max": 12288}


def aplicar_orcamento(payload, perfil, habilitado):
    if not habilitado or perfil != "apex":
        return
    if payload.get("thinking", {}).get("type") != "adaptive":
        return
    nivel = payload.get("output_config", {}).get("effort")
    if nivel in ORCAMENTO_APEX:
        budget = min(ORCAMENTO_APEX[nivel], payload.get("max_tokens", 4096) - 512)
        if budget > 0:
            payload.setdefault("extra_params", {})["reasoning_budget_tokens"] = budget


def esperar_servidor(consultar):
    prazo_ocupado = time.monotonic() + 1800
    prazo_carga = time.monotonic() + 120
    while True:
        try:
            slots = consultar("/slots")
        except HTTPError as erro:
            if erro.code != 503:
                raise
        except URLError as erro:
            if isinstance(erro.reason, ConnectionRefusedError):
                return
            raise
        except (ConnectionError, TimeoutError):
            pass
        else:
            if not any(slot["is_processing"] for slot in slots):
                return
            if time.monotonic() >= prazo_ocupado:
                raise TimeoutError("O modelo anterior continua em uso.")
            prazo_carga = time.monotonic() + 120
        if time.monotonic() >= prazo_carga:
            raise TimeoutError("O servidor não terminou de carregar em 120 s.")
        time.sleep(0.5)


@contextmanager
def trava_modelo(path):
    with path.open("a+b") as file:
        deadline = time.monotonic() + 1800
        while True:
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("O servidor continua ocupado.")
                time.sleep(0.2)
        try:
            yield
        finally:
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def roteador(backend, http, modelos, carregar, modelo_ativo, consultar, lock_path, *,
             orcamento_apex=False):
    key_path = lock_path.with_suffix(".key")
    if not key_path.exists():
        with trava_modelo(lock_path):
            if not key_path.exists():
                tmp = key_path.with_suffix(".key.tmp")
                tmp.write_text("sk-ant-local-" + secrets.token_hex(24), encoding="ascii")
                tmp.replace(key_path)
    token = key_path.read_text(encoding="ascii").strip()
    perfis = {modelo: perfil for perfil, modelo in modelos.items()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def resposta(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def erro(self, status, mensagem):
            self.resposta(status, {"type": "error", "error": {
                "type": "invalid_request_error" if status < 500 else "api_error",
                "message": mensagem,
            }})

        def autorizado(self):
            if secrets.compare_digest(self.headers.get("x-api-key", ""), token):
                return True
            self.erro(401, "Credencial local inválida.")
            return False

        def do_GET(self):
            if not self.autorizado():
                return
            if urlsplit(self.path).path != "/v1/models":
                self.erro(404, "Endpoint indisponível.")
                return
            self.resposta(200, {"data": [
                {"id": modelo, "type": "model", "display_name": nome,
                 "created_at": "2026-01-01T00:00:00Z"}
                for perfil, nome in (("cobaia", "Mellum"), ("apex", "Apex"), ("base", "Mellum base"))
                if (modelo := modelos.get(perfil))
            ], "has_more": False})

        def do_POST(self):
            if not self.autorizado():
                return
            path = urlsplit(self.path).path
            if path not in ("/v1/messages", "/v1/messages/count_tokens"):
                self.erro(404, "Endpoint indisponível.")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 64 * 1024 * 1024:
                    raise ValueError("Tamanho de mensagem inválido.")
                payload = json.loads(self.rfile.read(length))
                modelo = payload["model"].removesuffix("[1m]").removesuffix("[200k]")
                perfil = perfis[modelo]
                payload["model"] = modelo
            except (ValueError, KeyError, TypeError, AttributeError):
                self.erro(400, "Selecione um modelo local do menu e envie uma mensagem válida.")
                return

            try:
                with trava_modelo(lock_path):
                    if path == "/v1/messages":
                        esperar_servidor(consultar)
                        carregar(perfil)
                        aplicar_orcamento(payload, perfil, orcamento_apex)
                    else:
                        # Contagens auxiliares usam o modelo residente. A seleção
                        # só troca pesos quando chega uma requisição de geração.
                        esperar_servidor(consultar)
                        payload["model"] = modelo_ativo()
                    request = Request(backend + self.path, data=json.dumps(payload).encode(),
                                      headers={"Content-Type": "application/json"})
                    try:
                        response = http.open(request, timeout=1800)
                    except HTTPError as erro:
                        response = erro
                    with response:
                        self.encaminhando = True
                        self.send_response(response.code)
                        self.send_header("Content-Type", response.headers.get(
                            "Content-Type", "application/json"))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        while chunk := response.read1(8192):
                            self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as erro:
                self.close_connection = True
                if not getattr(self, "encaminhando", False):
                    self.erro(503, f"Falha no servidor local: {erro}")

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", token
        finally:
            server.shutdown()
            thread.join()
