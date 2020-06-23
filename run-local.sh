#!/bin/bash

set -eu

ENV_NAME=venv

CONTAINER_NAME=language-tool

if [[ $(docker ps -a) =~ ${CONTAINER_NAME} ]]; then
    echo "[INFO] drop existing container ${CONTAINER_NAME}"
    docker rm --force ${CONTAINER_NAME}
fi

docker run -d -p 8010:8010 --name ${CONTAINER_NAME} silviof/docker-languagetool

# shellcheck disable=SC1090
source ./${ENV_NAME}/bin/activate

# $1 => scandata_path
# $2 => work_dir
# $3 => Tesseract executors 
# $4 => Tesseract configuration
PATTERN=${1%/*}
python ocr_pipeline.py -s $PATTERN -w $2 -e $3 -m $4

# clean up
docker rm --force ${CONTAINER_NAME}
