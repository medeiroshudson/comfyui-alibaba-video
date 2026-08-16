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

## Atualização e rollback

O pipeline publica uma imagem por commit e o Kubernetes deve consumir somente
uma referência imutável `tag@sha256:digest`. O fluxo de atualização é:

1. Executar os testes e a validação estrutural da imagem.
2. Publicar a imagem e confirmar que o manifesto GHCR pode ser baixado sem autenticação.
3. Atualizar o `initContainer` para a nova tag SHA e o digest correspondente.
4. Validar com `kubectl kustomize` e `kubectl apply --dry-run=server`.
5. Aplicar somente a base do ComfyUI e aguardar o rollout.
6. Confirmar `initContainer=Completed`, `Ready=True`, zero restarts e `AlibabaTextToVideo` em `/object_info`.

O `initContainer` valida a presença de `__init__.py` e
`alibaba_video/node.py` antes e depois da cópia para o PVC. Se a imagem estiver
mal empacotada, ele deve falhar em vez de deixar o Pod pronto sem o node.

Para rollback, restaure o `tag@sha256:digest` anterior no Deployment, valide o
manifesto e reaplique o mesmo recurso. Preserve o PVC e o digest anterior até
que a nova versão esteja validada.

Releases versionadas são referências legíveis para humanos; o Deployment
continua fixado por digest, inclusive quando consumir uma release:

```text
ghcr.io/medeiroshudson/comfyui-alibaba-video:v0.1.0@sha256:<digest>
```

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
