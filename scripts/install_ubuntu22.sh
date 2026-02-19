#!/usr/bin/env bash
set -e

sudo apt update
sudo apt install -y \
  python3-venv python3-pip \
  libtbb12 libtbbmalloc2 \
  libunwind8

# 创建 venv
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install pyside6 numpy
