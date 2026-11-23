# VK Dev Local Agent

Agente de desenvolvimento local para Windows, com Claude Code, inferência por llama.cpp e observabilidade opcional pelo Prometheus e Grafana.

## Instalação

Instale Python com pip, Docker Desktop com Compose, WSL 2, suporte NVIDIA CUDA e Claude Code. Execute python -B instalar-agente.py, selecione a pasta, os modelos e as opções de observabilidade. O instalador verifica Docker e Compose. A GPU e o WSL precisam ser verificados na máquina de destino.

O instalador baixa os modelos selecionados por padrão. A imagem de inferência deve ser obtida na pasta instalada com docker compose -f compose.mellum-base.yaml pull llama-server.

AgenteLocal.exe inicia o agente. Com Grafana selecionado, AgenteLocalGrafana.exe também abre o painel local. Os perfis fornecidos usam 32.768 tokens de contexto e meta de 768 MiB livres de VRAM no carregamento.

Os pesos de modelos, credenciais, volumes e históricos permanecem fora do repositório. Componentes externos são obtidos separadamente e seguem suas próprias licenças. A licença dos arquivos próprios ainda não foi escolhida.

## Organização

- agente contém o lançador, o roteador e as instruções.
- instalacao contém os componentes auxiliares do instalador.
- inferencia contém os perfis Docker do servidor.
- observabilidade contém os serviços e o painel de métricas.

O instalador reúne os arquivos necessários na pasta escolhida para uso local.
