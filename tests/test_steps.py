# -*- coding: utf-8 -*-
"""Tests OCR API"""

import os
import shutil

import pytest

from lib.ocr_step import (
    StepIO,
    StepTesseract,
    StepPostMoveAlto,
    StepPostReplaceChars,
    # RegexReplacement,
    StepPostReplaceCharsRegex,
    StepPostRemoveFile,
    StepException,
    StepEstimateOCR,
    textlines2data,
    altolines2textlines,
)


def test_stepio_not_initable():
    """StepIO cant be instantiated"""

    with pytest.raises(TypeError) as exec_info:
        StepIO()    # pylint: disable=abstract-class-instantiated
    assert "Can't instantiate" in str(exec_info.value)


@pytest.fixture(name='path_tiff')
def fixture_path_existing(tmpdir):
    """supply valid path"""

    path = tmpdir.mkdir("scan").join("500_gray00001_st.tif")
    path.write_binary(bytearray([120, 3, 255, 0, 100]))
    return str(path)


def test_step_tesseract_list_langs(path_tiff):
    """Tesseract list-langs"""

    # arrange
    args = {'--list-langs': None}

    # act
    step = StepTesseract(args)
    step.path_in = path_tiff

    # assert
    assert ' --list-langs' in step.cmd
    assert step.path_in == path_tiff


def test_step_tesseract_path_out_folder(path_tiff):
    """Tesseract path to write result"""

    # arrange
    args = {'-l': 'deu', 'alto': None}

    # act
    step = StepTesseract(args)
    step.path_in = path_tiff

    # assert
    assert 'scan/500_gray00001_st.xml' in step.path_next


def test_step_tesseract_invalid_params(path_tiff):
    """Tesseract path to write result"""

    # act
    with pytest.raises(StepException) as excinfo:
        StepTesseract(path_tiff)

    # assert
    actual_exc_text = str(excinfo.value)
    assert 'Invalid Dictionary for arguments provided' in actual_exc_text
    assert '"need more than 1 value to unpack" !' in actual_exc_text


def test_step_tesseract_full_args(path_tiff):
    """Tesseract check cmd from args from following schema:
    'tesseract --dpi 500 <read_path> <out_path> -l <DEFAULT_CHARSET> alto'
    """

    # arrange
    # some args are computed later on
    args = {'--dpi': 470, '-l': 'ulbfrk', 'alto': None}

    # act
    step = StepTesseract(args)
    step.path_in = path_tiff

    # assert
    cmd = f'tesseract {path_tiff} {os.path.splitext(path_tiff)[0]} --dpi 470 -l ulbfrk alto'
    assert cmd == step.cmd
    assert step.path_next.endswith('500_gray00001_st.xml')


def test_step_tesseract_different_configurations(path_tiff):
    """Check cmd from args use different lang config"""

    # arrange
    args = {'-l': 'frk_ulbzd1', 'alto': None, 'txt': None}

    # act
    step = StepTesseract(args)
    step.path_in = path_tiff

    # assert
    tesseract_cmd = f'tesseract {path_tiff} {os.path.splitext(path_tiff)[0]} -l frk_ulbzd1 alto txt'
    assert tesseract_cmd == step.cmd


def test_step_copy_alto_back(path_tiff):
    """Move ALTO file back to where we started"""

    # arrange
    path_target = '/tmp/500_gray00001_st.tif'

    # act
    step = StepPostMoveAlto({})
    step.path_in = path_tiff
    step.path_next = path_target
    step.execute()

    # assert
    assert path_tiff == step.path_in
    assert step.path_next == '/tmp/500_gray00001_st.xml'
    assert os.path.exists(step.path_next)


def test_step_replace():
    """unittest replace func"""

    # arrange
    src = './tests/resources/500_gray00003.xml'
    dict_chars = {'ſ': 's', 'ic)': 'ich'}
    params = {'dict_chars': dict_chars, 'must_backup': True}
    step = StepPostReplaceChars(params)
    step.path_in = src

    lines = ['<String ID="string_405" WC="0.96" CONTENT="geweſen"/>']
    lines.append('<String ID="string_406" WC="0.95" CONTENT="iſt."/>')
    lines.append('<String ID="string_407" WC="0.96" CONTENT="Beſtätigt"/>')

    # act
    step._replace(lines)

    # assert
    assert len(step.lines_new) == 3
    assert not 'iſt.' in step.lines_new[1]
    assert 'ist.' in step.lines_new[1]
    assert step.must_backup()


@pytest.fixture(name='empty_ocr')
def fixture_empty_ocr(tmpdir):
    """create tmp data empty ALTO XML"""

    path = tmpdir.mkdir("xml").join("0041.xml")
    shutil.copyfile('./tests/resources/0041.xml', path)
    return str(path)


def test_step_replace_with_empty_alto(empty_ocr):
    """Determine behavior for invalid input data"""

    step = StepPostReplaceChars({'dict_chars': {'ſ': 's'}})
    step.path_in = empty_ocr

    # act
    step.execute()

    # assert
    assert not step.statistics


@pytest.fixture(name='tmp_500_gray')
def fixture_create_tmp_500_gray(tmpdir):
    """create tmp data from file 500_gray00003.xml"""

    path = tmpdir.mkdir("xml").join("input.xml")
    shutil.copyfile('./tests/resources/500_gray00003.xml', path)
    return path


def _provide_replace_params():
    dict_chars = {'ſ': 's', 'ic)': 'ich'}
    params = {'dict_chars': dict_chars, 'must_backup': True}
    return params


def test_replaced_file_written(tmp_500_gray):
    """test replaced file written"""

    # arrange
    params = _provide_replace_params()
    step = StepPostReplaceChars(params)

    # act
    step.path_in = tmp_500_gray
    step.execute()

    # assert
    check_handle = open(tmp_500_gray, 'r')
    lines = check_handle.readlines()
    for line in lines:
        for (k, _) in params['dict_chars'].items():
            assert k not in line
    check_handle.close()

    assert os.path.exists(os.path.join(os.path.dirname(tmp_500_gray),
                                       'input_before_StepPostReplaceChars.xml'))
    assert not os.path.exists(os.path.join(os.path.dirname(tmp_500_gray),
                                           'input_before_StepPostReplaceCharsRegex.xml'))


def test_replaced_file_statistics(tmp_500_gray):
    """test statistics available"""

    # arrange
    step = StepPostReplaceChars(_provide_replace_params())
    step.path_in = tmp_500_gray

    # act
    step.execute()

    # assert
    expected = ['ſ:392', 'ic):6']
    assert expected == step.statistics
    assert os.path.exists(os.path.join(os.path.dirname(tmp_500_gray),
                                       'input_before_StepPostReplaceChars.xml'))


def test_regex_replacements(tmp_500_gray):
    """check regex replacements in total"""

    # arrange
    params = {'pattern': r'([aeioubcglnt]3[:-]*")', 'old': '3', 'new': 's'}
    step = StepPostReplaceCharsRegex(params)

    # act
    step.path_in = tmp_500_gray
    step.execute()

    # assert
    assert not os.path.exists(os.path.join(os.path.dirname(str(tmp_500_gray)),
                                           'input_before_StepPostReplaceChars.xml'))
    with open(str(tmp_500_gray)) as test_handle:
        lines = test_handle.readlines()
        for line in lines:
            assert not 'u3"' in line, 'detected trailing "3" in ' + line

    expected = ['a3"=>as":5',
                'u3"=>us":1',
                'l3"=>ls":2',
                'e3"=>es":4',
                't3"=>ts":4',
                'c3"=>cs":1',
                'b3"=>bs":1',
                'i3"=>is":2',
                'g3"=>gs":1',
                'n3"=>ns":1']
    assert expected == step.statistics


def test_remove_failed():
    """Test remove failed since file is missing"""

    # arrange
    step = StepPostRemoveFile({'file_suffix': 'tif'})

    # act
    with pytest.raises(RuntimeError):
        step.path_in = 'qwerrwe.tif'


def test_remove_succeeded(path_tiff):
    """Test remove success"""

    # arrange
    step = StepPostRemoveFile({'file_suffix': 'tif'})

    # act
    step.path_in = path_tiff
    step.execute()

    # assert
    assert step.is_removed()


def test_stepestimateocr_analyze():
    """Analyse estimation results"""

    # arrange
    results = [
        ('0001.tif', 14.123),
        ('0002.tif', 18.123),
        ('0003.tif', 28.123),
        ('0004.tif', 38.123),
        ('0005.tif', 40.123),
        ('0006.tif', 41.123),
        ('0007.tif', 51.123),
        ('0008.tif', 60.123),
        ('0009.tif', 68.123),
        ('0010.tif', 68.123),
    ]

    # act
    actual = StepEstimateOCR.analyze(results)

    # assert
    assert actual[0] == 42.723
    assert len(actual[1]) == 5
    assert len(actual[1][0]) == 1
    assert len(actual[1][1]) == 2
    assert len(actual[1][2]) == 3
    assert len(actual[1][3]) == 1
    assert len(actual[1][4]) == 3


def test_estimate_handle_large_wtr():
    """Test handle border cases and large real wtr from 1667524704_J_0116/0936.tif"""

    # arrange
    results = [
        ('0001.tif', 0),
        ('0002.tif', 28.123),
        ('0003.tif', 41.123),
        ('0004.tif', 50.123),
        ('0936.tif', 78.571),
        ('0005.tif', 100.123),
    ]

    # act
    actual = StepEstimateOCR.analyze(results)

    # assert
    assert actual[0] == 49.677
    assert len(actual[1]) == 5
    assert len(actual[1][0]) == 1
    assert len(actual[1][1]) == 1
    assert len(actual[1][2]) == 1
    assert len(actual[1][3]) == 1
    assert len(actual[1][4]) == 2


def test_step_estimateocr_empty_alto(empty_ocr):
    """
    Determine bahavior of stepestimator when confronted with empty alto file
    Modified: in this (rare) case, just do nothing, do *not* raise any Exception
    """

    step = StepEstimateOCR({})
    step.path_in = empty_ocr

    # act
    step.execute()

    # assert
    assert step.statistics[0] == -1


def test_service_down():
    """Determine Behavior when url not accessible"""

    step = StepEstimateOCR({})
    assert not step.is_available()


def test_step_estimateocr_lines_and_tokens():
    """Test behavior of for valid ALTO-output"""

    test_data = os.path.join('tests', 'resources', '500_gray00003.xml')

    # act
    # pylint: disable=protected-access
    lines = altolines2textlines(test_data)
    (_, n_lines, _, _, n_lines_out) = textlines2data(lines)

    assert len(lines) == 370
    assert n_lines == 370
    assert n_lines_out == 350
