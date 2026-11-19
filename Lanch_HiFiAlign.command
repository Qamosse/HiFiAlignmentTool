#!/bin/zsh
# Change path to the "python" executable on the appropriate conda environment.
# Double-clic this file in the Finder to open HiFi Align (in the "multiplex" conda environment).
cd "$(dirname "$0")"
exec /opt/miniconda3/envs/multiplex/bin/python -m hifialign "$@"
