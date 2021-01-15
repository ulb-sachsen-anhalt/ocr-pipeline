#!/bin/bash

set -e

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
# $3 => image dpi
# $4 => Tesseract configuration

[[ $1 == */ ]] && PATTERN=${1%/*} || PATTERN=$1
if [ -n "$2" ]; then
    if [ -n "$3" ]; then
        if [ -n "$4" ]; then
            python ocr_pipeline.py -s "$PATTERN" -w $2 -d $3 -m $4
        else
            python ocr_pipeline.py -s "$PATTERN" -w $2 -d $3
        fi
    else
        python ocr_pipeline.py -s "$PATTERN" -w $2 
    fi
else
    python ocr_pipeline.py -s "$PATTERN" -w workdir/tmp 
fi


# clean up
docker rm --force ${CONTAINER_NAME}
