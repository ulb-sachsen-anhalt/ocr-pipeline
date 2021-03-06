# ULB Sachsen-Anhalt - OCR System

![Python application](https://github.com/ulb-sachsen-anhalt/ocr-pipeline/workflows/Python%20application/badge.svg)

OCR-System of project "Digitalisierung historischer deutscher Zeitungen" (2019-2021). Processes large chunks of bare Imagefiles and creates a corresponding OCR-Output in ALTO-XML V3 format for each file using the OpenSource Engine [Tesseract-OCR](https://github.com/tesseract-ocr/tesseract).

## Features

* configuration
  * OCR pipeline `conf/ocr_config.ini`
  * logging `conf/ocr_logger_config.ini`
* supports custom Tesseract models
* run in Docker for mass digitisation purposes
* run locally for evaluation and testing
* optional language tool container for quality evaluation of OCR output

## Installation

### Requirements

* [Docker Container](https://www.docker.com/get-started)
* [Ubuntu 18.04 LTS Server](https://ubuntu.com/#download) or higher

optional:
* libsm6 (if OpenCV used)
* python3-venv (if Python is used outside Container, i.e. running Tests)

#### Hardware recommendation

Minimal:
* 8GB RAM
* quadcore processor

Recommended:
* 16GB RAM
* sixteen-core processor

### Build container image

The OCR-Container is built in 2 stages.

All dockerfiles can be found in the [container](https://github.com/ulb-sachsen-anhalt/ocr-pipeline/tree/master/container) folder.
The base image contains a self-compiled version of Tesseract, cloned from <https://github.com/ulb-sachsen-anhalt/tesseract> plus localization. The base Tesseract container images does not come with any trained models. Please download the ones you require manually to your localhost and map the `tessdata`dir to the container.
The second step is to build the OCR system image. It puts the scripts in place, declares an entrypoint, copies additional model data and takes care of internal structures that can be mapped at runtime to external images, workdir and logdir folders. The model dir enables users to add own trained models to the workflow, rather than relying on standard models.

```shell
# 1st: build base image from official Tesseract Release Tag and with desired image name. We're using 4.1.1 until a new stable version is released.
./create-baseimage.sh my-tesseract:4.1.1
=> my-tesseract:4.1.1

# 2nd: build ocr system image using the previously created base image + tag and desired name and version tag and optional model from the model dir
./create-image.sh my-tesseract:4.1.1 my-ocr-system:1.0.0 <my-model.traineddata>
=> my-ocr-system:1.0.0

```

#### local execution

It is possible to texecute the pipeline locally without additional container logic for testing and evaluation purposes. This way, any models can be used as above. 

```shell
python ./ocr_pipeline.py --scandata <required> --workdir <optional, default is local folder> --dpi <specify resolution, default is 300> --executors <optional> --models <multiple can be chained with +>
```

## Development

### Setup

For local development, an installation of Python3 (version 3.6+) is required. For coding assistance, supply your favourite IDE with Python support. If you don't know which one to choose, we recommend [Visual Studio Code](https://code.visualstudio.com/). The Development started on Ubuntu 18.04 with Python 3.6.

The Tesseract Instances use Python's `concurrent.futures.ProcessPoolExecutor` implementation and are therefore plattform dependent. It has issues both on Mac OS (Mojave) and Windows (10) and also depends on the specific Python Version.  

For local development it's also required to have a local Tesseract Installation with any required model configurations. 

Activate virtual Python environment and install required libraries on a Windows System:

```bash

# windows
python -m venv venv
venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r requirements.txt
pip install -r tests/tests_requirements.txt

```

Afterwards, the [pytest Library](https://docs.pytest.org/en/latest/contents.html) is used to execute the current test cases from directory `tests/` (with verbosity flag `v`)

```bash
pytest -v
```

## OCR as part of Digitalization Pipelines

OCR is usually just a part of larger Digitalization Workflows. 

The script `manage-container-ocr.sh` forms the OCR part of the Digitization Workflow at ULB Sachsen-Anhalt, which spans itself from the image source to delivering data towards the final presentation system of the library. These integration may differ in other Digitalization contexts, when the OCR Process is triggered by different mechanics.

Data delivery to the host system is scheduled via cronjobs. When triggered, it's searching a small marker file called `meta_done`, which represents the previous stage in the workflow. After running the OCR-System, this marker file is moved on as `ocr_done`, which indicates the following step to continue since OCR has sucessfully finished.
