# VK Dev Local Agent

> **Prova de conceito (PoC):** este projeto é experimental e está em desenvolvimento. Os agentes configurados pelo instalador automático têm autonomia limitada: podem precisar de instruções detalhadas, acompanhamento e intervenção manual para planejar, executar, corrigir e validar tarefas. Seus resultados podem ser inconsistentes e devem ser revisados e testados pelo usuário; a instalação não garante execução autônoma confiável nem desempenho equivalente ao de serviços pagos.

Agente de desenvolvimento local para Windows, com Claude Code, inferência por llama.cpp e observabilidade opcional pelo Prometheus e Grafana.

## Tecnologias

[![Claude Code](https://img.shields.io/badge/Claude%20Code-agente-D97757?logo=claude&logoColor=white)](https://code.claude.com/docs/)
[![llama.cpp](https://img.shields.io/badge/llama.cpp-infer%C3%AAncia%20local-4A5568)](https://github.com/ggml-org/llama.cpp)
[![Mellum](https://img.shields.io/badge/Mellum-12B%20MoE-7B61FF)](https://huggingface.co/JetBrains/Mellum2.1-12B-A2.5B-Thinking-GGUF)
[![Apex](https://img.shields.io/badge/Apex-35B%20MoE-6741D9)](https://huggingface.co/Apexintelligence-AI/Apex-35B-V1.0-GGUF)
[![Python](https://img.shields.io/badge/Python-agente%20e%20instalador-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![WSL 2](https://img.shields.io/badge/Windows-WSL%202-0078D4)](https://learn.microsoft.com/windows/wsl/)
[![NVIDIA CUDA](https://img.shields.io/badge/NVIDIA-CUDA-76B900?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-toolkit)
[![Prometheus](https://img.shields.io/badge/Prometheus-m%C3%A9tricas-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-pain%C3%A9is-F46800?logo=grafana&logoColor=white)](https://grafana.com/oss/grafana/)

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

## Desinstalação

Em instalações novas, execute `Desinstalar Agente.cmd` na pasta do agente. A interface pede confirmação e permite optar pela exclusão dos arquivos dos modelos selecionados na instalação e pela remoção dos contêineres associados àquela pasta. Os arquivos instalados que foram alterados e quaisquer arquivos não reconhecidos são preservados. Instalações anteriores, sem manifesto, exigem remoção manual.

As opções de modelos e contêineres ficam desmarcadas por padrão. A remoção dos contêineres exige Docker acessível e confere a pasta registrada nos rótulos do Compose; recursos compartilhados ou de outra pasta são preservados. Volumes e imagens Docker, dados de monitoramento, rede, tarefa agendada do coletor de hardware e dependências como Docker, WSL, Python e Claude Code não são removidos pelo desinstalador.

## Monitoramento padrão

Ao selecionar Grafana na instalação, o painel **Inferência local** apresenta:

- Tokens de entrada e de geração por segundo, além dos totais acumulados.
- Requisições em processamento e em espera, maior contexto observado e disponibilidade da coleta.
- RAM do contêiner, incluindo memória anônima e cache de arquivos.
- RAM total e disponível da VM WSL.
- VRAM total, ocupada e livre da GPU.
- Swap em uso pela VM WSL e pelo contêiner.
- Soma da memória residente dos processos Claude Code.

O painel abre com seis horas de histórico e atualização a cada 15 segundos. A coleta de hardware começa após a ativação do coletor no Windows. A VRAM representa a GPU inteira, e a RAM do contêiner inclui cache de arquivos. [Abrir o Grafana local](http://127.0.0.1:3000/d/llm-inferencia/inferencia-local)
