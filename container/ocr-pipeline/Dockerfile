ARG BASE_IMAGE
ARG BASE_IMAGE_TAG

FROM ${BASE_IMAGE}:${BASE_IMAGE_TAG}

# set frontend non-interactive to silence 'debconf: unable to initialiaze frontend'
ARG DEBIAN_FRONTEND=noninteractive

# set target OCR_ROOT
ENV OCR_ROOT /opt/ocr-pipeline

# update software repositories
RUN ["apt-get", "update"]
RUN apt-get update && apt-get install -y \
    python3-pip 

# create OCR_ROOT dir inside container ...
RUN ["mkdir", "-p", "${OCR_ROOT}"]

# ... and now enter target dir
WORKDIR ${OCR_ROOT}

# for workdir use same folder as on host
RUN ["mkdir", "workdir"]
# for logs use same folder as on host
RUN ["mkdir", "logdir"]

# copy application data into workdir
COPY ./ocr_pipeline.py .
COPY ./conf/ ./conf
COPY ./lib/ ./lib
COPY ./requirements.txt .
RUN ["pip3", "install", "-r", "requirements.txt"]

# copy all traineddata files from subdir model
COPY ./model/*.traineddata /usr/local/share/tessdata/

# create scandata target folder inside container
# for scandata root use same folder name as on host
RUN ["mkdir", "/data"]
