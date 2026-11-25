#!/bin/sh
cd "$(dirname "$0")/.." || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "还没有虚拟环境。请先看 README 的安装步骤。" >&2
  exit 1
fi
export PYTHONPATH=src
exec .venv/bin/python -m screenmatch
