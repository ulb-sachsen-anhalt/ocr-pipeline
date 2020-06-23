#!/bin/bash

set -eu

CONTAINER_NAMES=('ocr-pipeline-102020-01-13' 'ocr-pipeline-10' 'ocr-pipeline-12')

BASE_IMAGE=$1
BASE_IMAGE_TAG=$2
IMAGE=$3
IMAGE_TAG=$4
TESS_MODEL=$5
DOCKER_FILE=Dockerfile

# throw old containers away to be able to delete preceeding image, too
for CONT in ${CONTAINER_NAMES[*]}
do
    docker rm --force "${CONT}" || echo "[INFO] no container named ${CONT} ... "
done

# remove container image or note absence
docker image rm "${IMAGE}:${IMAGE_TAG}" || echo "[WARN] image ${IMAGE}:${IMAGE_TAG} not existing ... "

# re-build container from scratch (no caches)
docker build --no-cache \
    --network=host \
    --build-arg BASE_IMAGE="${BASE_IMAGE}" \
    --build-arg BASE_IMAGE_TAG="${BASE_IMAGE_TAG}" \
    --build-arg TESS_MODEL="${TESS_MODEL}" \
    -t "${IMAGE}:${IMAGE_TAG}" \
    -f ${DOCKER_FILE} .
