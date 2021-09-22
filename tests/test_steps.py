# -*- coding: utf-8 -*-
"""Tests OCR API"""

import json
import os
import pathlib
import shutil

from unittest import (
    mock
)

import xml.etree.ElementTree as ET

import requests

import pytest

from lib.ocr_step import (
    NAMESPACES,
    StepIO,
    StepTesseract,
    StepPostMoveAlto,
    StepPostReplaceChars,
    # RegexReplacement,
    StepPostReplaceCharsRegex,
    StepPostRemoveFile,
    StepException,
    StepEstimateOCR,
    StepPostprocessALTO,
    textlines2data,
    altolines2textlines,
)

PROJECT_ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_stepio_not_initable():
    """StepIO cant be instantiated"""

    with pytest.raises(TypeError) as exec_info:
        StepIO()    # pylint: disable=abstract-class-instantiated
    assert "Can't instantiate" in str(exec_info.value)


TIF_001 = '001.tif'
TIF_002 = '002.tif'


@pytest.fixture(name='max_dir')
def fixture_path_existing(tmp_path):
    """supply valid path"""

    max_dir = tmp_path / 'MAX'
    max_dir.mkdir()
    path1 = max_dir / TIF_001
    path1.write_bytes(bytearray([120, 3, 255, 0, 100]))
    path2 = max_dir / TIF_002
    path2.write_bytes(bytearray([120, 3, 255, 0, 100]))
    return str(max_dir)


def test_step_tesseract_list_langs(max_dir):
    """Tesseract list-langs"""

    # arrange
    args = {'--list-langs': None}

    # act
    step = StepTesseract(args)
    step.path_in = os.path.join(max_dir, TIF_001)

    # assert
    assert ' --list-langs' in step.cmd


def test_step_tesseract_path_out_folder(max_dir):
    """Tesseract path to write result"""

    # arrange
    args = {'-l': 'deu', 'alto': None}

    # act
    step = StepTesseract(args)
    step.path_in = os.path.join(max_dir, TIF_001)

    # assert
    assert '001.xml' in step.path_next


def test_step_tesseract_change_input(max_dir):
    """Tesseract path to write result"""

    # arrange
    args = {'-l': 'deu', 'alto': None}

    # act
    step = StepTesseract(args)
    step.path_in = os.path.join(max_dir, TIF_001)

    # assert
    assert 'MAX/001.tif ' in step.cmd
    assert 'MAX/001.xml ' not in step.cmd
    assert 'MAX/001 ' in step.cmd

    # re-act
    step.path_in = os.path.join(max_dir, TIF_002)

    # re-assert
    assert 'MAX/001.tif ' not in step.cmd
    assert 'MAX/002.tif ' in step.cmd
    assert 'MAX/002 ' in step.cmd


def test_step_tesseract_change_input_with_dir(max_dir):
    """Tesseract path to write result"""

    # arrange
    args = {'-l': 'deu', 'alto': None}

    # act
    step = StepTesseract(args)
    step.path_in = os.path.join(max_dir, TIF_001)

    # assert
    assert 'MAX/001.tif ' in step.cmd
    assert 'MAX/001 ' in step.cmd

    # re-act
    step.path_in = os.path.join(max_dir, TIF_002)

    # re-assert
    assert 'MAX/001.tif ' not in step.cmd
    assert 'MAX/002.tif ' in step.cmd
    assert 'MAX/002 ' in step.cmd


def test_step_tesseract_invalid_params(max_dir):
    """Tesseract path to write result"""

    # act
    with pytest.raises(StepException) as excinfo:
        StepTesseract(max_dir)

    # assert
    actual_exc_text = str(excinfo.value)
    assert 'Invalid Dictionary for arguments provided' in actual_exc_text
    assert '"need more than 1 value to unpack" !' in actual_exc_text


def test_step_tesseract_full_args(max_dir):
    """Tesseract check cmd from args from following schema:
    'tesseract --dpi 500 <read_path> <out_path> -l <DEFAULT_CHARSET> alto'
    """

    # arrange
    # some args are computed later on
    args = {'--dpi': 470, '-l': 'ulbfrk', 'alto': None}

    # act
    step = StepTesseract(args)
    step.path_in = os.path.join(max_dir, TIF_001)

    # assert
    input_tif = os.path.join(max_dir, TIF_001)
    output_xml = os.path.splitext(os.path.join(max_dir, TIF_001))[0]
    cmd = f'tesseract {input_tif} {output_xml} --dpi 470 -l ulbfrk alto'
    assert cmd == step.cmd
    assert step.path_next.endswith('001.xml')


def test_step_tesseract_different_configurations(max_dir):
    """Check cmd from args use different lang config"""

    # arrange
    args = {'-l': 'frk_ulbzd1', 'alto': None, 'txt': None}

    # act
    step = StepTesseract(args)
    step.path_in = os.path.join(max_dir, TIF_001)

    # assert
    input_tif = os.path.join(max_dir, TIF_001)
    output_xml = os.path.splitext(os.path.join(max_dir, TIF_001))[0]
    tesseract_cmd = f'tesseract {input_tif} {output_xml} -l frk_ulbzd1 alto txt'
    assert tesseract_cmd == step.cmd


def test_step_copy_alto_back(max_dir):
    """
    Move ALTO file back to where we started
    Preserve filename, only switch directory
    """

    # arrange
    path_target = '/tmp/500_gray00001_st.tif'

    # act
    step = StepPostMoveAlto({})
    step.path_in = os.path.join(max_dir, TIF_001)
    step.path_next = path_target
    step.execute()

    # assert
    assert os.path.join(max_dir, TIF_001) == step.path_in
    assert step.path_next == '/tmp/001.xml'
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
    check_handle = open(tmp_500_gray, 'r', encoding="UTF-8")
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


def test_remove_succeeded(max_dir):
    """Test remove success"""

    # arrange
    step = StepPostRemoveFile({'file_suffix': 'tif'})

    # act
    step.path_in = os.path.join(max_dir, TIF_001)
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


@mock.patch("requests.head")
def test_service_down(mock_requests):
    """Determine Behavior when url not accessible"""

    # arrange
    params = {'service_url': 'http://localhost:8010/v2/check'}
    step = StepEstimateOCR(params)
    mock_requests.side_effect = requests.ConnectionError

    # assert
    assert not step.is_available()
    assert mock_requests.called == 1


def test_step_estimateocr_textline_conversions():
    """Test functional behavior for valid ALTO-output"""

    test_data = os.path.join('tests', 'resources', '500_gray00003.xml')

    # act
    # pylint: disable=protected-access
    lines = altolines2textlines(test_data)
    (_, n_lines, _, _, n_lines_out) = textlines2data(lines)

    assert len(lines) == 370
    assert n_lines == 370
    assert n_lines_out == 346

# pylint: disable=unused-argument


def _fixture_languagetool(*args):
    result = mock.Mock()
    result.status_code = 200
    response_path = os.path.join(PROJECT_ROOT_DIR, 'tests', 'resources',
                                 'languagetool_response_500_gray00003.json')
    with open(response_path, encoding="UTF-8") as the_json_file:
        result.json.return_value = json.load(the_json_file)
    return result


@mock.patch("requests.post")
def test_step_estimateocr_lines_and_tokens(mock_requests):
    """Test behavior of for valid ALTO-output"""

    # arrange
    test_data = os.path.join(PROJECT_ROOT_DIR,
                             'tests', 'resources', '500_gray00003.xml')
    mock_requests.side_effect = _fixture_languagetool
    params = {'service_url': 'http://localhost:8010/v2/check',
              'language': 'de-DE',
              'enabled_rules': 'GERMAN_SPELLER_RULE'
              }
    step = StepEstimateOCR(params)
    step.path_in = test_data

    # act
    step.execute()

    assert step.statistics
    assert mock_requests.called == 1


@mock.patch("requests.get")
def test_stepestimate_invalid_data(mock_request):
    """
    Check that in case of *really empty* data,
    language-tool is not called after all
    """

    # arrange
    data_path = os.path.join(
        PROJECT_ROOT_DIR, 'tests/resources/1667524704_J_0173_0173.xml')
    params = {'service_url': 'http://localhost:8010/v2/check',
              'language': 'de-DE',
              'enabled_rules': 'GERMAN_SPELLER_RULE'
              }
    step = StepEstimateOCR(params)
    step.path_in = data_path

    # act
    step.execute()

    # assert
    assert step.statistics
    assert not mock_request.called


def test_clear_empty_content(tmp_path):
    """Ensure no more empty Strings exist"""

    test_data = os.path.join('tests', 'resources', '16331011.xml')
    prev_root = ET.parse(test_data).getroot()
    prev_strings = prev_root.findall('.//alto:String', NAMESPACES)
    assert len(prev_strings) == 275
    dst_path = tmp_path / "16331011.xml"
    shutil.copy(test_data, dst_path)
    step = StepPostprocessALTO()
    step.path_in = dst_path

    # act
    step.execute()

    # assert
    xml_root = ET.parse(dst_path).getroot()
    all_strings = xml_root.findall('.//alto:String', NAMESPACES)
    # assert about 20 Strings have been dropped due emptyness
    assert len(all_strings) == 254
    assert xml_root.find(
        './/alto:fileIdentifier',
        NAMESPACES).text == '16331011'
    assert xml_root.find('.//alto:fileName', NAMESPACES).text == '16331011.xml'


def test_clear_empty_lines_with_spatiums(tmp_path):
    """Ensure no more empty Strings exist"""

    test_data = os.path.join('tests', 'resources', '16331001.xml')
    prev_root = ET.parse(test_data).getroot()
    prev_strings = prev_root.findall('.//alto:String', NAMESPACES)
    # original ALTO output
    assert len(prev_strings) == 1854
    dst_path = tmp_path / "16331001.xml"
    shutil.copy(test_data, dst_path)
    step = StepPostprocessALTO()
    step.path_in = dst_path

    # act
    step.execute()

    # assert
    xml_root = ET.parse(dst_path).getroot()
    all_strings = xml_root.findall('.//alto:String', NAMESPACES)
    # line with 2 empty strings and SP in between
    line_with_sps = xml_root.findall(
        './/alto:TextLine[@ID="line_2"]', NAMESPACES)
    assert not line_with_sps
    # assert many Strings have been dropped due emptyness
    assert len(all_strings) == 1673
    assert xml_root.find(
        './/alto:fileIdentifier',
        NAMESPACES).text == '16331001'
    assert xml_root.find('.//alto:fileName', NAMESPACES).text == '16331001.xml'
