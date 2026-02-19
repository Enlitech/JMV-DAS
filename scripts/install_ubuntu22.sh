#!/usr/bin/env bash
set -e

sudo apt update
sudo apt install -y \
  python3-venv python3-pip \
  libtbb12 libtbbmalloc2 \
  libunwind8

sudo apt install -y \
  libxcb-cursor0 \
  libxcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \
  libxkbcommon-x11-0 \
  libxrender1 libxi6 libxext6 libx11-6 \
  libgl1

# 创建 venv
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
