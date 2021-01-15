#!/bin/bash

# force abort on error
set -eu


# script constants
CNT_OCR_ROOT=/opt/ulb/ocr
CNT_OCR_N_EXECUTOR=4
CNT_OCR_LOGDIR=${CNT_OCR_ROOT}/log
CNT_OCR_WORKDIR=${CNT_OCR_ROOT}/workdir

# main
# $1 => host_scandata_path
# $2 => container image
# $3 => container name
# $4 => dpi images
# $5 => tesseract model config
#
OPEN_FOLDER=$1
CONTAINER_IMAGE=$2
CONTAINER_NAME=$3
DPI=$4
TESSERACT_MODEL=$5

HOST_CURRENT_DIR=$(pwd)
HOST_WORKDIR=${HOST_CURRENT_DIR}/workdir/${OPEN_FOLDER##*/}
HOST_LOGDIR=${HOST_CURRENT_DIR}/log

# create local sub-workdirectory
if [ -d "${HOST_WORKDIR}" ]; then
    echo "[WARN] remove existing workdir '${HOST_WORKDIR}'"
fi
echo "[INFO] create workdir '${HOST_WORKDIR}'"
mkdir -p "${HOST_WORKDIR}"

CNT_SCANDATA=/home/ocr

# drop container if exists
docker rm ${CONTAINER_NAME} || echo "[INFO] container '${CONTAINER_NAME} not existing'"

# create
echo "[INFO] create container '${CONTAINER_NAME}' from image '${CONTAINER_IMAGE}"
echo "[INFO] mounts open_folder '${OPEN_FOLDER}' => '${CNT_SCANDATA}'"
echo "[INFO] mounts workdir '${HOST_WORKDIR}' => '${CNT_OCR_WORKDIR}'"
echo "[INFO] mounts log '${HOST_LOGDIR}' => '${CNT_OCR_LOGDIR}'"

docker create --name ${CONTAINER_NAME} \
    --mount type=bind,source="${OPEN_FOLDER}",target=${CNT_SCANDATA} \
    --mount type=bind,source="${HOST_WORKDIR}",target="${CNT_OCR_WORKDIR}" \
    --mount type=bind,source="${HOST_LOGDIR}",target=${CNT_OCR_LOGDIR} \
    ${CONTAINER_IMAGE} python3 ocr_pipeline.py -s ${CNT_SCANDATA} -w ${CNT_OCR_WORKDIR} -m ${TESSERACT_MODEL} -d ${DPI}

# run
echo "[INFO] start '${CONTAINER_NAME}' and attach to logs"
docker start ${CONTAINER_NAME} && docker logs -f ${CONTAINER_NAME}
