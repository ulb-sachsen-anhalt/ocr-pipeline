# -*- coding: utf-8 -*-
"""Tests OCR Pipeline API"""

import logging
import os
import pathlib
import shutil
import configparser

import pytest

from ocr_pipeline import (
    OCRPipeline,
    profile
)
from lib.ocr_step import (
    StepTesseract,
    StepPostReplaceChars,
    StepPostReplaceCharsRegex
)

RES_0001_TIF = "0001.tif"
RES_0002_PNG = "0002.png"
RES_0003_JPG = "0003.jpg"
RES_00041_XML = './tests/resources/0041.xml'


@pytest.fixture(name="a_workspace")
def fixure_a_workspace(tmp_path):
    """create 08/15 workspace fixture"""

    data_dir = tmp_path / "scandata"
    data_dir.mkdir()
    log_dir = tmp_path / "log"
    log_dir.mkdir()

    path_scan_0001 = data_dir / RES_0001_TIF
    path_scan_0002 = data_dir / RES_0002_PNG
    path_scan_0003 = data_dir / RES_0003_JPG
    path_mark_prev = data_dir / "ocr_pipeline_open"
    with open(path_mark_prev, 'w', encoding="UTF-8") as marker_file:
        marker_file.write("some previous state\n")

    shutil.copyfile(RES_00041_XML, path_scan_0001)
    shutil.copyfile(RES_00041_XML, path_scan_0002)
    shutil.copyfile(RES_00041_XML, path_scan_0003)

    log_dir = log_dir / 'ocr-pipeline-log'
    return tmp_path


@pytest.fixture(name="default_pipeline")
def _fixture_default_pipeline(a_workspace):
    data_dir = a_workspace / "scandata"
    log_dir = a_workspace / "log"
    return OCRPipeline(str(data_dir), log_dir=str(log_dir))


def test_ocr_pipeline_default_config(default_pipeline):
    """check default config options"""

    # act once
    pipeline = default_pipeline

    # assert
    assert pipeline
    assert pipeline.cfg.get('pipeline', 'executors') == '8'
    assert pipeline.cfg.get('pipeline', 'logger_name') == 'ocr_pipeline'
    assert pipeline.cfg.get('pipeline', 'file_ext') == 'tif,jpg,png,jpeg'
    assert pipeline.cfg.get('step_03', 'language') == 'de-DE'
    assert pipeline.cfg.get('step_03', 'enabled_rules') == 'GERMAN_SPELLER_RULE'


def test_ocr_pipeline_default_logging(default_pipeline, caplog):
    """check default config options"""

    # arrange
    log_msg = 'this is a test log info message'

    # act
    caplog.set_level(logging.INFO, logger="ocr_pipeline")
    default_pipeline.logger.info(log_msg)

    # assert log data
    assert log_msg in caplog.messages


def test_ocr_pipeline_config_merged(default_pipeline):
    """check how mix of config and cli-args interfere"""

    # arrange
    extra_val = "--tessdata-dir /usr/share/tesseract-ocr/4.00/tessdata --dpi 452"
    args = {"scandata": "/tmp/ocr-pipeline",
            "executors": "2",
            "extra": extra_val
            }

    # act
    pipeline = default_pipeline
    pipeline.merge_args(args)

    # assert
    assert pipeline.cfg['step_01']
    assert extra_val in pipeline.cfg['step_01']['extra']
    assert 'tesseract' in pipeline.cfg['step_01']['tesseract_bin']


def test_ocr_pipeline_config_merge_without_extra(default_pipeline):
    """check how mix of config and cli-args without dpi"""

    cp = configparser.ConfigParser()
    test_dir = os.path.dirname(os.path.dirname(__file__))
    conf_file = os.path.join(test_dir, 'conf', 'ocr_config.ini')
    cp.read(conf_file)

    # arrange
    args = {"scandata": "/tmp/ocr-pipeline",
            "executors": "2",
            "models": "ara",
            "extra": "''"}

    # act
    pipeline = default_pipeline
    pipeline.merge_args(args)

    # assert
    assert pipeline.cfg.getint('pipeline', 'executors') == 2
    assert pipeline.cfg['step_01']['model_configs'] == 'ara'

    step1 = pipeline.get_steps()[0]
    step1.path_in = os.path.join(default_pipeline.data_path, RES_0001_TIF)

    assert "''" not in step1.cmd
    assert step1.cmd.endswith('0001 -l ara alto')


def test_ocr_pipeline_mark_done(default_pipeline):
    """check marker file changed"""

    # act like something has happened
    default_pipeline.input_sorted()
    default_pipeline.lock_paths()
    # ... ocr-ing
    default_pipeline.mark_done()

    # assert
    default_scanpath = default_pipeline.data_path
    new_mark_path = os.path.join(default_scanpath, 'ocr_pipeline_done')
    assert os.path.exists(new_mark_path)
    with open(new_mark_path, 'r', encoding="UTF-8") as f_han:
        entries = f_han.readlines()
        last_entry = entries[-1]
        assert last_entry.endswith('mark state ocr_pipeline_done')


def test_ocr_pipeline_get_images(default_pipeline):
    """check images are sorted"""

    # act
    images = default_pipeline.input_sorted()
    default_scanpath = default_pipeline.data_path

    # assert
    assert images
    assert os.path.join(default_scanpath, RES_0001_TIF) in images
    assert os.path.join(default_scanpath, RES_0002_PNG) in images
    assert os.path.join(default_scanpath, RES_0003_JPG) in images
    assert os.path.join(default_scanpath, RES_0001_TIF) == images[0]
    assert os.path.join(default_scanpath, RES_0002_PNG) == images[1]
    assert os.path.join(default_scanpath, RES_0003_JPG) == images[2]


def test_ocr_pipeline_prepare_workdir(default_pipeline):
    """check default workspace setup"""

    # act
    default_pipeline.prepare_workdir()

    # assert
    assert default_pipeline.cfg.get('pipeline', 'workdir')\
        == '/opt/ocr-pipeline/workdir'


def test_ocr_pipeline_profile():
    """check profiling"""

    # arrange
    # pylint: disable=missing-class-docstring,too-few-public-methods
    class InnerClass:

        # pylint: disable=missing-function-docstring,no-self-use
        def func(self):
            return [i * i for i in range(1, 2000000)]

    # act
    inner = InnerClass()
    result = profile(inner.func)
    assert "'test_ocr_pipeline_profile' passed in" in result


def test_ocr_pipeline_estimations(default_pipeline):
    """check estimation data persisted"""

    # arrange
    estms = [('0001.tif', 21.476, 3143, 675, 506, 29, 24, 482),
             ('0002.png', 38.799, 1482, 575, 193, 11, 34, 159),
             ('0003.jpg', 39.519, 582, 230, 152, 2, 12, 140)]

    # act
    wtr_path = default_pipeline.store_estimations(estms)

    # assert
    assert os.path.exists(wtr_path)


@pytest.fixture(name="custom_config_pipeline")
def _fixture_custom_config_pipeline(a_workspace):
    data_dir = a_workspace / "scandata"
    log_dir = a_workspace / "log"
    conf_dir = a_workspace / "conf"
    conf_dir.mkdir()
    conf_file = pathlib.Path(__file__).parent / \
        'resources' / 'ocr_config_full.ini'
    assert os.path.isfile(conf_file)
    return OCRPipeline(str(data_dir), log_dir=str(
        log_dir), conf_file=str(conf_file))


def test_pipeline_step_tesseract(custom_config_pipeline, a_workspace):
    """Check proper tesseract cmd from full configuration"""

    # act
    steps = custom_config_pipeline.get_steps()
    steps[0].path_in = a_workspace / 'scandata' / RES_0001_TIF

    # assert
    assert len(steps) == 5
    assert isinstance(steps[0], StepTesseract)
    the_cmd = steps[0].cmd
    the_cmd_tokens = the_cmd.split()
    assert len(the_cmd_tokens) == 6
    assert the_cmd_tokens[0] == 'tesseract'
    assert the_cmd_tokens[1].endswith('scandata/0001.tif')
    assert the_cmd_tokens[2].endswith('scandata/0001')
    assert the_cmd_tokens[3] == '-l'
    assert the_cmd_tokens[4] == 'frk+deu'
    assert the_cmd_tokens[5] == 'alto'


@pytest.fixture(name="recursive_workspace")
def _recursive_workspace(tmp_path):
    """create workspace fixture with 2 sub dirs"""

    img_root = tmp_path / "scans"
    img_root.mkdir()
    scan_dir01 = img_root / "scandata1"
    scan_dir01.mkdir()
    scan_dir02 = img_root / "scandata2"
    scan_dir02.mkdir()
    log_dir = tmp_path / "log"
    log_dir.mkdir()

    path_scan_0001 = scan_dir01 / RES_0001_TIF
    path_scan_0002 = scan_dir02 / RES_0003_JPG
    shutil.copyfile(RES_00041_XML, path_scan_0001)
    shutil.copyfile(RES_00041_XML, path_scan_0002)

    log_dir = log_dir / 'ocr-pipeline-log'
    return tmp_path


def test_pipeline_gather_images_recursevly(recursive_workspace):
    """Behavior OCR-Input collected in sub dirs with one open"""

    # arrange
    marker_file = recursive_workspace / "scans" / "scandata2" / "ocr_pipeline_open"
    marker_file.write_text("opened")
    log_dir = recursive_workspace / "log"
    pipeline = OCRPipeline(str(recursive_workspace), log_dir=str(log_dir))

    # act
    input_paths = pipeline.input_sorted(recursive=True)

    # assert
    assert len(input_paths) == 1
    assert "scans/scandata2/0003.jpg" in input_paths[0]


def test_pipeline_step_replace(custom_config_pipeline):
    """Check proper steps from full configuration"""

    # act
    steps = custom_config_pipeline.get_steps()

    # assert
    assert len(steps) == 5
    assert isinstance(steps[1], StepPostReplaceChars)
    assert isinstance(steps[1].dict_chars, dict)


def test_pipeline_step_replace_regex(custom_config_pipeline):
    """Check proper steps from full configuration"""

    # act
    steps = custom_config_pipeline.get_steps()

    # assert
    assert len(steps) == 5
    assert isinstance(steps[2], StepPostReplaceCharsRegex)
    assert steps[2].pattern == 'r\'([aeioubcglnt]3[:-]*")\''


def test_pipeline_gather_images_recursive_with_marks(recursive_workspace):
    """
    OCR-Input is collected from several sub dirs
    and path-locking works as expected
    """

    # arrange
    scan_dir03 = recursive_workspace / "scans" / "scandata3"
    scan_dir03.mkdir()
    path_a_scan = scan_dir03 / RES_0003_JPG
    path_dir01_busy = recursive_workspace / \
        "scans" / "scandata1" / "ocr_pipeline_open"
    with open(path_dir01_busy, 'w', encoding="UTF-8") as marker_file:
        marker_file.write("previous state\n")
    shutil.copyfile(RES_00041_XML, path_a_scan)

    log_dir = recursive_workspace / "log"
    pipeline = OCRPipeline(str(recursive_workspace), log_dir=str(log_dir))

    # act
    input_paths = pipeline.input_sorted(recursive=True)
    pipeline.lock_paths()

    # assert
    assert len(input_paths) == 1
    assert "scans/scandata1/0001.tif" in input_paths[0]
    # check the two dirs have been locked as expected
    assert os.path.exists(
        str(recursive_workspace / "scans" / "scandata1" / "ocr_pipeline_busy"))

    # re-check: now these paths won't be taken into account anymore
    assert not pipeline.input_sorted(recursive=True)


def test_pipeline_gather_images_from_dirs_with_marks(recursive_workspace):
    """
    OCR-Input is filtered from 2 different scandata_dirs
    and path-locking works as expected
    """

    # arrange
    path_dir01_open = recursive_workspace / \
        "scans" / "scandata1" / "ocr_pipeline_open"
    path_dir02 = recursive_workspace / "scans" / "scandata2"
    with open(path_dir01_open, 'w', encoding="UTF-8") as marker_file:
        marker_file.write("previous state\n")
    log_dir = recursive_workspace / "log"
    dirs = os.path.dirname(path_dir01_open) + ',' + str(path_dir02)
    pipeline = OCRPipeline(dirs, log_dir=str(log_dir))

    # act
    input_paths = pipeline.input_sorted()
    pipeline.lock_paths()

    # assert
    assert len(input_paths) == 1
    assert "scans/scandata1/0001.tif" in input_paths[0]
    # check the two dirs have been locked as expected
    assert os.path.exists(
        str(recursive_workspace / "scans" / "scandata1" / "ocr_pipeline_busy"))

    # re-check: now these paths won't be taken into account anymore
    assert not pipeline.input_sorted()
