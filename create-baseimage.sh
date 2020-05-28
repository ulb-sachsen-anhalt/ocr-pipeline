#!/bin/bash

set -eu

TESSERACT_RELEASE=$1
IMAGE_TAG_PREFIX=$2
DOCKER_CONF=Dockerfile-tesseract
TESSERACT_REPOSITORY=https://github.com/ulb-sachsen-anhalt/tesseract.git

docker build --build-arg TESSERACT_RELEASE=${TESSERACT_RELEASE} --build-arg TESSERACT_REPOSITORY=${TESSERACT_REPOSITORY} --tag ${IMAGE_TAG_PREFIX}:${TESSERACT_RELEASE} -f ${DOCKER_CONF} .
