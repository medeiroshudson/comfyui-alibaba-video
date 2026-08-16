# ComfyUI Alibaba Token Plan video node

Custom node para geração hosted de vídeo text-to-video usando o endpoint nativo do Alibaba Model Studio/Token Plan.

## MVP

Workflow:

```text
AlibabaTextToVideo → SaveVideo
```

Modelo habilitado nesta versão:

```text
happyhorse-1.1-t2v
```

O cliente usa:

- `POST /api/v1/services/aigc/video-generation/video-synthesis`;
- `X-DashScope-Async: enable`;
- polling em `GET /api/v1/tasks/{task_id}`;
- download de `video/mp4` com limite de tamanho;
- validação opcional por `ffprobe`;
- redaction de tokens, headers e URLs assinadas.

## Runtime

As credenciais são lidas somente durante a execução do node:

```text
AI_ALIBABA_API_ENDPOINT
AI_ALIBABA_API_KEY
```

Os valores não pertencem ao workflow, à imagem nem ao repositório.

## Imagem de artefato

A imagem publicada em GHCR contém somente o addon em:

```text
/opt/comfyui-addon/custom_nodes/ComfyUI-Alibaba-Video
```

Ela é consumida pelo `initContainer` do ComfyUI, que copia o diretório para o volume de custom nodes do runtime. A imagem não contém a distribuição completa do ComfyUI e não executa inferência por conta própria.

Imagem pública:

```text
ghcr.io/medeiroshudson/comfyui-alibaba-video
```

Use sempre uma tag fixada por digest em ambientes de produção.

## Testes

```bash
uv run --no-project --with pytest python -m pytest tests -q
python3 -m compileall -q alibaba_video custom_nodes
```

## GitHub Actions

- `ci.yml` executa os testes e `compileall`.
- `container.yml` publica a imagem no GHCR em pushes para `main` e tags `v*`.
- Pull requests executam validação, mas não publicam imagens.
- A publicação usa provenance e SBOM.

## Limites desta versão

- somente text-to-video;
- somente `happyhorse-1.1-t2v`;
- sem image-to-video;
- sem parâmetros fictícios de seed ou prompt extension.

## Segurança

Não coloque credenciais, URLs assinadas, dumps de ambiente ou workflows de implantação neste repositório. A chave deve ser fornecida exclusivamente pelo ambiente de execução protegido.

## Licença

MIT. Consulte `LICENSE`.
