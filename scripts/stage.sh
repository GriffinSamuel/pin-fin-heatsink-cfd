#!/usr/bin/env bash
# Mirror the repo (without work/) to the staging area used to push files to the laptop.
SRC=/home/claude/heatsink-cfd; DST=/mnt/user-data/outputs/heatsink-cfd
mkdir -p "$DST"
cd "$SRC" && find . -type f ! -path './work/*' ! -path './.pytest_cache/*' ! -path '*/__pycache__/*' ! -path './.git/*' | while read -r f; do
  mkdir -p "$DST/$(dirname "$f")"; cp -p "$f" "$DST/$f"; done
cp "$SRC/Makefile" "$DST/Makefile.txt"
find "$DST" -type f | sed "s#$DST/##" | sort
