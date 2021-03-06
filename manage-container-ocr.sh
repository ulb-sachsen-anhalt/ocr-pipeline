#!/bin/bash

set -e


##################
#
# Script constants
#
# host dirs - adapt tp your needs
OCR_ROOT_DIR=/data/ocr/zd1
OCR_ROOT_HOST=/opt/ocr-pipeline

# container dirs - should'n be touched
OCR_ROOT_CNT=/opt/ocr-pipeline
OCR_STAGE_PREV="meta_done"
OCR_STAGE_BUSY="ocr_busy"
CONTAINER_LT="ocr-languagetool"


function restart_languagetool {
    if [[ $(docker ps -a) =~ ${CONTAINER_LT} ]]; then
        echo "[INFO ] drop existing container ${CONTAINER_LT}"
        docker rm --force ${CONTAINER_LT}
    fi
    docker run -d -p 8010:8010 --name ${CONTAINER_LT} silviof/docker-languagetool
}


# $1 => name of ocr-pipeline container to forward tiff-data
# $2 => numbers of process executors (8/12/16)
# $3 => pipeline 1=scantailor , 2=opencv?
function process_open_folders {
    # we really want to use path expansion here
    # shellcheck disable=SC2086
    FIRST_OPEN_PATH=$(find ${OCR_DIR} -type f -name "${OCR_STAGE_PREV}" | sort | head -n 1)
    # if nothing open, stop
    if [ "" == "${FIRST_OPEN_PATH}" ]; then
        echo "[INFO ] no open folders need to be processed in '${OCR_DIR}', work done"
        return
    else
        # diagnostic echo
        for OPEN_PATH in ${FIRST_OPEN_PATH}
        do
            echo "[DEBUG] detected FIRST OPEN PATH '${OPEN_PATH}'"
        done
    fi

    # get path minus file
    OPEN_FOLDER=$(dirname "${FIRST_OPEN_PATH}")
    # pick last path segment
    OPEN_PATH_FOLDER=${OPEN_FOLDER##*/}
    # check if container is running
    echo "[DEBUG] inspect state of container '${CONTAINER_NAME}' (folder: '${OPEN_PATH_FOLDER}')"
    LS_CONTAINERS=$(docker container ls -q --filter name="${CONTAINER_NAME}")
   
    if [ -z "${LS_CONTAINERS}" ]; then    
        echo "[INFO ] container '${CONTAINER_NAME}' idle, can be used for path ${OPEN_PATH_FOLDER}"
        # restart language tool
        restart_languagetool

        # prepare new workdir
        WORKDIR_SUB=${OCR_ROOT_HOST}/workdir/${OPEN_PATH_FOLDER}
        # check state of new workdir
        if [ -d "${WORKDIR_SUB}" ]; then
            echo "[WARN ] found existing workdir ${WORKDIR_SUB}"
            #rm -rf "${WORKDIR_SUB}"
            TS=$(date +%Y-%d-%m-%H-%M)
            WORKDIR_SUB="${WORKDIR_SUB}_${TS}"
        else
            echo "[INFO ] creating new workdir ${WORKDIR_SUB}"
            # create workdir or die
        fi
        mkdir "${WORKDIR_SUB}" || exit 1

        # forward container re-creation
        recreate_container "${OPEN_PATH_FOLDER}"

        # start re-created container
        echo "[START] start container ${CONTAINER_NAME}"
        docker start "${CONTAINER_NAME}"

        # wait for container to start and to set marker BUSY
        sleep 20s

        # set marker
        mv "${OPEN_FOLDER}/${OCR_STAGE_PREV}" "${OPEN_FOLDER}/${OCR_STAGE_BUSY}"
        echo "state ${BUSY_STATE} : $(hostname):${OPEN_FOLDER}' at $(date '+%Y-%m-%d_%H:%M:%S')" >> "${OPEN_FOLDER}/${OCR_STAGE_BUSY}"
    else
        INFO=$(echo "${LS_CONTAINERS}" | awk '{print $1} {print $8} {print $9} {print $10}')
        NOTE=""
        for S in ${INFO}
        do
            NOTE="${NOTE} ${S}"
        done
        echo "[BUSY ] container '${CONTAINER_NAME}' ('${NOTE:1}') already busy, skip execution"
        # print busy message only once, then leave function immediatly
        return

    fi
}

function recreate_container {
    local folder=$1

    echo -e "[INFO ] check presence of Container '${CONTAINER_NAME}' ..."
    LS_CONTAINERS=$(docker container ls -a -q --filter name="${CONTAINER_NAME}")
    if [ -z "${LS_CONTAINERS}" ]; then
            echo -e "[INFO ] container '${CONTAINER_NAME}' not existing"
    else
        echo -e "[WARN ] container '${CONTAINER_NAME}' exists, must be removed"
        docker container rm "${CONTAINER_NAME}"
    fi

    OCR_HOST_WORKDIR=${WORKDIR_SUB}
    OCR_SCANDATA_HOST=${OCR_ROOT_DIR}/${folder}
    OCR_SCANDATA_CONT=/data/${folder}

    if [ ! -d "${OCR_SCANDATA_HOST}" ]; then
        echo "[ERROR] invalid scandata path '${OCR_SCANDATA_HOST}' on host system! Exit process"
        exit 1
    fi

    if [ -d "${OCR_HOST_WORKDIR}" ]; then
        echo "[WARN ] remove existing workdir ${OCR_HOST_WORKDIR}"
    fi
    echo "[INFO ] create workdir ${OCR_HOST_WORKDIR}"
    mkdir -p "${OCR_HOST_WORKDIR}"

    # check scandata mapping
    echo "[INFO ] map HOST ${OCR_SCANDATA_HOST} to CONTAINER ${OCR_SCANDATA_CONT}"

    docker create --name "${CONTAINER_NAME}" \
    --user "${CONTAINER_USER}" \
    --network host \
    --mount type=bind,source="${OCR_SCANDATA_HOST}",target="${OCR_SCANDATA_CONT}" \
    --mount type=bind,source="${OCR_HOST_WORKDIR}",target="${OCR_ROOT_CNT}"/workdir \
    --mount type=bind,source="${OCR_ROOT_HOST}"/logdir,target="${OCR_ROOT_CNT}"/logdir \
    "${CONTAINER_IMAGE}" python3 ocr_pipeline.py -s "${OCR_SCANDATA_CONT}" -w "${OCR_ROOT_CNT}"/workdir -e "${EXECUTORS}" -m "${MODEL_CONFIG}" -d "${DPI}"
}


########
# MAIN #
########
# $1 => Docker: container image
# $2 => Docker: container name
# $3 => Docker: user:group (numeric) that runs the container and can access host data shares
# $4 => OCR: local directory of data-share, accepts find-patterns (i.e. "/data/ocr/1667524704_01*")
# $5 => OCR: number of Tesseract-Executors (depending on host CPUs, i.e. 6|10|12)
# $6 => OCR: DPI of Images
# $7 => OCR: Tesseract-Model configuration to use (i.e. "frk", "custom_model_01")
######

CONTAINER_IMAGE=${1}
CONTAINER_NAME=${2}
CONTAINER_USER=$3
OCR_DIR=$4
EXECUTORS=$5
DPI=$6
MODEL_CONFIG=$7

echo "[INFO ] container-management with args '${*}'"

process_open_folders
