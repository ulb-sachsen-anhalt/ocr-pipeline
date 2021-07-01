#!/bin/bash

set -e


##################
#
# Script constants
#
# host dirs - shared by nfs mount for all workers
OCR_ROOT_HOST=/data/ocr

# Docker: user:group (numeric) that runs the container and can access host data shares
# FA account "ocr:ocr"
CONTAINER_USER="567:40367"

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


function process_open_folders {
    # we really want to use path expansion here - eat this, shellcheck:
    # shellcheck disable=SC2086
    FIRST_OPEN_PATH=$(find ${DATA_ROOT_DIR} -type f -name "${OCR_STAGE_PREV}" | sort | head -n 1)
    # if nothing open, stop
    if [ "" == "${FIRST_OPEN_PATH}" ]; then
        echo "[INFO ] no open folders need to be processed in '${DATA_ROOT_DIR}', work done"
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
        OCR_ROOT_WORKDIR=${OCR_ROOT_HOST}/workdir/${OPEN_PATH_FOLDER}
        # check state of new workdir
        if [ -d "${OCR_ROOT_WORKDIR}" ]; then
            echo "[WARN ] found existing workdir ${OCR_ROOT_WORKDIR}"
            #rm -rf "${OCR_ROOT_WORKDIR}"
            TS=$(date +%Y-%d-%m-%H-%M)
            OCR_ROOT_WORKDIR="${OCR_ROOT_WORKDIR}_${TS}"
        else
            echo "[INFO ] creating new workdir ${OCR_ROOT_WORKDIR}"
            # create workdir or die
        fi
        mkdir "${OCR_ROOT_WORKDIR}" || exit 1

        # forward container re-creation
        recreate_container "${OPEN_FOLDER}"

        # start re-created container
        echo "[START] start container ${CONTAINER_NAME}"
        docker start "${CONTAINER_NAME}"

        # wait for container to start and to set marker BUSY
        sleep 5s

        # set marker
        mv "${OPEN_FOLDER}/${OCR_STAGE_PREV}" "${OPEN_FOLDER}/${OCR_STAGE_BUSY}"
        echo "state ${OCR_STAGE_BUSY} at $(hostname):${OPEN_FOLDER}' at $(date '+%Y-%m-%d_%H:%M:%S')" >> "${OPEN_FOLDER}/${OCR_STAGE_BUSY}"
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
    local open_path=$1
    if [ ! -d "${open_path}" ]; then
        echo "[ERROR] invalid scandata path '${open_path}' on host system! Exit process"
        exit 1
    fi
    
    # pick last path segment
    local open_path_dir=${open_path##*/}

    echo -e "[INFO ] check presence of Container '${CONTAINER_NAME}' ..."
    LS_CONTAINERS=$(docker container ls -a -q --filter name="${CONTAINER_NAME}")
    if [ -z "${LS_CONTAINERS}" ]; then
            echo -e "[INFO ] container '${CONTAINER_NAME}' not existing"
    else
        echo -e "[WARN ] container '${CONTAINER_NAME}' exists, must be removed"
        docker container rm "${CONTAINER_NAME}"
    fi

    OCR_SCANDATA_CONT=/data/${open_path_dir}
    echo "[INFO ] map HOST ${open_path} to CONTAINER ${OCR_SCANDATA_CONT}"

    docker create --name "${CONTAINER_NAME}" \
    --user "${CONTAINER_USER}" \
    --network host \
    --mount type=bind,source="${open_path}",target="${OCR_SCANDATA_CONT}" \
    --mount type=bind,source="${OCR_ROOT_WORKDIR}",target="${OCR_ROOT_CNT}"/workdir \
    --mount type=bind,source="${OCR_ROOT_HOST}"/logdir,target="${OCR_ROOT_CNT}"/logdir \
    "${CONTAINER_IMAGE}" python3 ocr_pipeline.py "${OCR_SCANDATA_CONT}" -w "${OCR_ROOT_CNT}"/workdir -e "${EXECUTORS}" -m "${MODEL_CONFIG}" -x "${EXTRA}"
}


########
# MAIN #
########
# $1 => Docker: container image
# $2 => Docker: container name
# $3 => OCR: local data directory, accepts find-patterns (i.e. "/data/ocr/1667524704_01*")
# $4 => OCR: Tesseract-Model configuration to use (i.e. "frk", "custom_model_01")
# $5 => EXTRA: extra Tesseract parameters passed as repeatable pairs "--<key_1> <value_1>[ --<key_n> <value_n>]"
######

CONTAINER_IMAGE=${1}
CONTAINER_NAME=${2}
DATA_ROOT_DIR=${3}
# OCR: number of Tesseract-Executors (depending on host CPUs, i.e. 6|10|12), pick from container label suffix
# i.e. "ocr-pipeline-14" => "14"
EXECUTORS=${CONTAINER_NAME##*-}
MODEL_CONFIG=${4}
EXTRA=${5}

echo "[INFO ] container-management with args '${*}'"

process_open_folders
