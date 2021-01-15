# -*- coding: utf-8 -*-
"""Tests OCR Pipeline API"""

import os
import shutil
import tempfile

import pytest

from ocr_pipeline import (
    OCRPipeline
)



@pytest.fixture(name="default_pipeline")
def create_default_pipeline(tmpdir):
    """create tmp tif data dir"""

    path_dir = tmpdir.mkdir("scandata")
    path_scan_0001 = path_dir.join("0001.tif")
    path_scan_0002 = path_dir.join("0002.png")
    path_scan_0003 = path_dir.join("0003.jpg")
    path_mark_prev = path_dir.join("ocr_busy")
    with open(path_mark_prev, 'w') as marker_file:
        marker_file.write("previous state\n")

    shutil.copyfile('./test/resources/0041.xml', path_scan_0001)
    shutil.copyfile('./test/resources/0041.xml', path_scan_0002)
    shutil.copyfile('./test/resources/0041.xml', path_scan_0003)

    return OCRPipeline(str(path_dir))


def test_ocr_pipeline_default_config(default_pipeline):
    """check default config options"""

    # act once
    pipeline = default_pipeline

    # assert
    assert pipeline
    assert pipeline.get('pipeline', 'executors') == '8'
    assert pipeline.get('pipeline', 'logger_name') == 'ocr_pipeline'
    assert pipeline.get('pipeline', 'image_ext') == 'tif,jpg,png'
    assert pipeline.get('step_language_tool', 'language') == 'de-DE'
    assert pipeline.get('step_language_tool', 'enabled_rules') == 'GERMAN_SPELLER_RULE'

    # act again
    pipeline.log('info', 'this is a test log info message')

    # assert log data
    tld = os.path.join(tempfile.gettempdir(), 'log-ocr-pipeline')
    assert os.path.exists(tld)
    log_files = [os.path.join(tld, f) for f in os.listdir(tld) if str(f).endswith('.log')]
    log_files.sort(key=os.path.getmtime)
    assert log_files[0]
    with open(os.path.join(tld, log_files[0]), 'r') as f_han:
        entry = f_han.readline().strip()
        assert entry.endswith('[INFO ] this is a test log info message')


def test_ocr_pipeline_mark_done(default_pipeline):
    """check marker file changed"""

    # act
    default_pipeline.mark_done()

    # assert
    default_scanpath = default_pipeline.scanpath()
    new_mark_path = os.path.join(default_scanpath, 'ocr_done')
    assert os.path.exists(new_mark_path)
    with open(new_mark_path, 'r') as f_han:
        entries = f_han.readlines()
        last_entry = entries[-1]
        assert last_entry.endswith('switch to state ocr_done')


def test_ocr_pipeline_get_images(default_pipeline):
    """check all images are respected and sorted, too"""

    # act
    images = default_pipeline.get_images_sorted()
    default_scanpath = default_pipeline.scanpath()

    # assert
    assert images
    assert os.path.join(default_scanpath, "0001.tif") in images
    assert os.path.join(default_scanpath, "0002.png") in images
    assert os.path.join(default_scanpath, "0003.jpg") in images
    assert os.path.join(default_scanpath, "0001.tif") == images[0]
    assert os.path.join(default_scanpath, "0002.png") == images[1]
    assert os.path.join(default_scanpath, "0003.jpg") == images[2]


def test_ocr_pipeline_prepare_workdir(default_pipeline):
    """check default workspace setup"""

    # act
    workdir = default_pipeline.prepare_workdir()

    # assert
    assert workdir == '/tmp/ocr-pipeline-work'


def test_ocr_pipeline_profile(default_pipeline):
    """check profiling"""

    # arrange
    # pylint: disable=missing-class-docstring,too-few-public-methods 
    class InnerClass:

        # pylint: disable=missing-function-docstring,no-self-use
        def func(self):
            return [i*i for i in range(1, 2000000)]

    # act
    inner = InnerClass()
    result = default_pipeline.profile(inner.func)
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
