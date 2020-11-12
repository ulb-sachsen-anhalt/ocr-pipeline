ARG BASE_IMAGE
ARG BASE_IMAGE_TAG
ARG TESS_MODEL

FROM ${BASE_IMAGE}:${BASE_IMAGE_TAG}

# set frontend non-interactive to silence 'debconf: unable to initialiaze frontend'
ARG DEBIAN_FRONTEND=noninteractive

# set target OCR_ROOT
ENV OCR_ROOT /opt/ulb/ocr

# update software repositories
RUN ["apt-get", "update"]
# installs of libsm6, libext6, libxrender-dev necessary to fix
# opencv-python-docker issue: 'libsm shared object not found'
# see https://github.com/NVIDIA/nvidia-docker/issues/864
RUN apt-get update && apt-get install -y \
    python3-pip \
    libsm6 \
    libxext6 \
    libxrender-dev

# create OCR_ROOT dir inside container ...
RUN ["mkdir", "-p", "/opt/ulb/ocr"]

# ... and now enter target dir
WORKDIR ${OCR_ROOT}

# copy application data into workdir
COPY ./ocr_pipeline.py .
COPY ./conf/ ./conf
COPY ./lib/ ./lib
COPY ./requirements.txt .
RUN ["pip3", "install", "-r", "requirements.txt"]

# not fail copy if TESS_MODEL not existing, it will match .gitignore at least
COPY ./model/${TESS_MODEL} /usr/local/share/tessdata

# create scandata target folder inside container
# for scandata root use same folder name as on host
RUN ["mkdir", "/home/ocr"]
# for workdir use same folder as on host
RUN ["mkdir", "/opt/ulb/ocr/workdir"]
# for logs use same folder as on host
RUN ["mkdir", "/opt/ulb/ocr/logdir"]
