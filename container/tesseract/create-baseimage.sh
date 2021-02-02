#!/bin/bash

set -eu

IMAGE=${1}
TESSERACT_REF=${2}
DOCKER_CONF=container/tesseract/Dockerfile
TESSERACT_REPOSITORY=https://github.com/tesseract-ocr/tesseract.git

cd ../..

docker build --no-cache \
    --build-arg TESSERACT_REF="${TESSERACT_REF}" \
    --build-arg TESSERACT_REPOSITORY=${TESSERACT_REPOSITORY} \
    --tag "${IMAGE}" \
    -f ${DOCKER_CONF} .
