"""Baixa os GGUFs do comparativo em blocos retomáveis no M:."""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest, sha256
from pathlib import Path
from subprocess import run
from urllib.parse import quote

from caminhos_locais import modelos_instalados


MODELS = {
    "apex": (
        "Apexintelligence-AI/Apex-35B-V1.0-GGUF",
        "c585fe8de7387925133ab7a573916c2d7070d714",
        "Apex-35B-V1.0-IQ3_XS.gguf",
        16795650208,
        "709740b8400cf490126eb8d35439dbee0bfad56cdb0bde61b2f10026a7850122",
    ),
    "mellum": (
        "JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF",
        "4159d684ffdb09ba89dc2a58feb3e75c54eef036",
        "Mellum2.1-12B-A2.5B-Thinking-Q4_K_M.gguf",
        8071295264,
        "ecc4d5b8107fc219e23c494b2d107552137637b6c6002ee713e0ba8af7fa2755",
    ),
    "mellum-mtp": (
        "JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF",
        "4159d684ffdb09ba89dc2a58feb3e75c54eef036",
        "mtp/Mellum2.1-12B-A2.5B-Thinking-MTP-Q4_K_M.gguf",
        8329317344,
        "51fe54045179ee755bcca8c18a7acdc2bc861203a67e129f20dcd80ff6fbaa4c",
    ),
    "qwen": (
        "unsloth/Qwen3.6-35B-A3B-GGUF",
        "a483e9e6cbd595906af30beda3187c2663a1118c",
        "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf",
        17730509792,
        "649d7508507b84638732c4f52c24c8b15843c6dca2f3ff793ae07c14a67ebbb3",
    ),
}
BLOCK_SIZE = 8 * 1024**2


def download(model, workers, root):
    repo, revision, remote_path, size, expected_hash = MODELS[model]
    filename = Path(remote_path).name
    target = root / filename
    if target.exists():
        with target.open("rb") as source:
            actual_hash = file_digest(source, "sha256").hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"SHA256 divergente em {target}")
        print(f"Verificado: {target}", flush=True)
        return

    url = f"https://huggingface.co/{repo}/resolve/{revision}/{quote(remote_path)}"
    parts = root / ".blocos-8mib" / revision / filename
    parts.mkdir(parents=True, exist_ok=True)
    count = (size + BLOCK_SIZE - 1) // BLOCK_SIZE

    def fetch(index):
        start = index * BLOCK_SIZE
        end = min(start + BLOCK_SIZE, size) - 1
        length = end - start + 1
        block = parts / f"{index:05d}.block"
        if block.exists() and block.stat().st_size == length:
            return block
        partial = block.with_suffix(".partial")
        result = run(
            ["curl.exe", "--silent", "--show-error", "--fail", "--location",
             "--range", f"{start}-{end}", "--max-filesize", str(length),
             "--connect-timeout", "15", "--max-time", "60", "--retry", "2",
             "--output", str(partial), "--write-out", "%{http_code}", url],
            capture_output=True,
            text=True,
        )
        if result.returncode or result.stdout != "206" or partial.stat().st_size != length:
            raise RuntimeError(f"Bloco {index} de {filename}: curl={result.returncode}, HTTP={result.stdout}")
        partial.replace(block)
        return block

    blocks = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for completed, block in enumerate(pool.map(fetch, range(count), buffersize=2 * workers), 1):
            blocks.append(block)
            if completed == 1 or completed % 16 == 0 or completed == count:
                print(f"{model}: {completed}/{count} blocos", flush=True)

    assembled = target.with_suffix(".gguf.assembling")
    digest = sha256()
    with assembled.open("wb") as output:
        for block in blocks:
            data = block.read_bytes()
            output.write(data)
            digest.update(data)
    if digest.hexdigest() != expected_hash:
        raise ValueError(f"SHA256 divergente em {assembled}")
    assembled.rename(target)
    for block in blocks:
        block.unlink()
    parts.rmdir()
    print(f"Verificado: {target} | SHA256 {expected_hash}", flush=True)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=8,
                        metavar="1-16", help="Número de blocos baixados em paralelo")
    parser.add_argument("--destino", type=Path, help="Pasta onde serão gravados os modelos")
    parser.add_argument("models", nargs="+", choices=MODELS)
    args = parser.parse_args()
    root = args.destino or modelos_instalados(Path(__file__).resolve().parent) or Path(r"M:\LLM\llama.cpp\models")
    root.mkdir(parents=True, exist_ok=True)
    for selected in args.models:
        download(selected, args.workers, root)
