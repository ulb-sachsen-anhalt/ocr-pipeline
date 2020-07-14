#!/bin/bash

ENV_NAME=venv
if [ ! -d ${ENV_NAME} ]; then
    python3 -m venv ${ENV_NAME}
fi

# shellcheck disable=SC1090
source ./${ENV_NAME}/bin/activate 
pip install --upgrade pip
pip install -r requirements.txt

pytest --cov-report html --cov=lib --cov=ocr_pipeline test/ -v
