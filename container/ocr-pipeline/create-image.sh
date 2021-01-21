#!/bin/bash

set -e

#####
#
# create custom ocr-pipeline image
#
# $1 => basis container image as name:tag, i.e. my-custom-tesseract:1.0.0
# $2 => create image in format name:tag, i.e. my-pipeline:3.0.0
# $3 => name the container that will be created from image specification from arg $2
# $4 => opt. model config to be included. convenient to include custom traineddata
#
BASE_IMAGE=${1/:*/}
BASE_IMAGE_TAG=${1/*:/}
IMAGE=${2/:*/}
IMAGE_TAG=${2/*:/}
CONTAINER_NAME=$3
TESS_MODEL=$4

#
# clear eventually existing images and containers
# 
# throw container away to be able to delete preceeding image, too
docker rm --force "${CONTAINER_NAME}" || echo "[INFO] no container named ${CONTAINER_NAME} existing ... "
# remove container image or note absence
docker image rm "${IMAGE}:${IMAGE_TAG}" || echo "[WARN] no image ${IMAGE}:${IMAGE_TAG} existing ... "

# go to project root dir for full build context
cd ../..

# re-build container from scratch (no caches)
docker build --no-cache \
    --network=host \
    --build-arg BASE_IMAGE="${BASE_IMAGE}" \
    --build-arg BASE_IMAGE_TAG="${BASE_IMAGE_TAG}" \
    --build-arg TESS_MODEL="${TESS_MODEL}" \
    -t "${IMAGE}:${IMAGE_TAG}" \
    -f container/ocr-pipeline/Dockerfile .
