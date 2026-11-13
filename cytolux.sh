#!/bin/bash
# Start Cytolux. Arguments: a .fgw workspace or a folder of FCS files (optional).
export PYTHONNOUSERSITE=1
cd "$HOME/cytolux" && exec "$HOME/miniconda3/envs/flowgate/bin/python" -m cytolux "$@"
