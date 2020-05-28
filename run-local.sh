#!/bin/bash

set -eu

ENV_NAME=venv

python3 -m venv venv
source ./${ENV_NAME}/bin/activate

# $1 => scandata_path
# $2 => work_dir
# $x => executors fixed to 3 for local Desktop PC
python ocr_pipeline.py -s $1 -w $2 -e 3 -m $3
