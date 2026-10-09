#!/bin/bash
# Start FlowGate. Arguments: a .fgw workspace or a folder of FCS files (optional).
export PYTHONNOUSERSITE=1
cd "$HOME/flowgate" && exec "$HOME/miniconda3/envs/flowgate/bin/python" -m flowgate "$@"
