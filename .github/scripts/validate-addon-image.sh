#!/bin/sh
set -eu

image=${1:?usage: validate-addon-image.sh IMAGE}

docker run --rm "$image" sh -ceu '
  addon=/opt/comfyui-addon/custom_nodes/ComfyUI-Alibaba-Video

  test -f "$addon/__init__.py"
  test -f "$addon/alibaba_video/node.py"
  test ! -e /opt/comfyui
  test -z "$(find /opt/comfyui-addon -type d -name __pycache__ -print -quit)"
  test -z "$(find /opt/comfyui-addon -type f \( -name ".env" -o -name "*.secret" -o -name "*.token" \) -print -quit)"

  if grep -R -qiE "renda-extra|renda_extra" /opt/comfyui-addon; then
    echo "legacy project reference found in addon image" >&2
    exit 1
  fi

  python -c "import sys; sys.path.insert(0, '/opt/comfyui-addon/custom_nodes/ComfyUI-Alibaba-Video'); import alibaba_video.node"
'

echo "addon image validation passed: $image"
