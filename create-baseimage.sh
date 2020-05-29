#!/bin/bash

set -eu

IMAGE_NAME=$1
TESSERACT_RELEASE=$2
DOCKER_CONF=Dockerfile-tesseract
TESSERACT_REPOSITORY=https://github.com/ulb-sachsen-anhalt/tesseract.git

docker build --build-arg TESSERACT_RELEASE="${TESSERACT_RELEASE}" --build-arg TESSERACT_REPOSITORY=${TESSERACT_REPOSITORY} --tag "${IMAGE_NAME}:${TESSERACT_RELEASE}" -f ${DOCKER_CONF} .
