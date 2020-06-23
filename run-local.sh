#!/bin/bash

set -eu

ENV_NAME=venv

CONTAINER_NAME=language-tool

if [[ $(docker ps -a) =~ ${CONTAINER_NAME} ]]; then
    echo "[INFO] drop existing container ${CONTAINER_NAME}"
    docker rm --force ${CONTAINER_NAME}
fi

docker run -d -p 8010:8010 --name ${CONTAINER_NAME} silviof/docker-languagetool

source ./${ENV_NAME}/bin/activate

# $1 => scandata_path
# $2 => work_dir
# $x => executors fixed to 3 for local Desktop PC
python ocr_pipeline.py -s $1 -w $2 -e 3 -m $3
