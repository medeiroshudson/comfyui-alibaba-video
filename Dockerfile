FROM python:3.13-slim

WORKDIR /opt/comfyui-addon

COPY alibaba_video ./alibaba_video
COPY custom_nodes ./custom_nodes

RUN python -m compileall -q alibaba_video custom_nodes

LABEL org.opencontainers.image.title="ComfyUI Alibaba Token Plan video node"
LABEL org.opencontainers.image.description="Hosted Alibaba Model Studio Token Plan video generation node for ComfyUI"
LABEL org.opencontainers.image.source="https://github.com/medeiroshudson/comfyui-alibaba-video"

CMD ["sh", "-c", "sleep infinity"]
