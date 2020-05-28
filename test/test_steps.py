# -*- coding: utf-8 -*-
"""Tests OCR API"""

import os
import shutil

import pytest

from lib.ocr_step import (
    Step,
    StepIO,
    StepTesseract,
    StepPostMoveAlto,
    StepPostReplaceChars,
    RegexReplacement,
    StepPostReplaceCharsRegex,
    StepPostRemoveFile,
    StepException
)



def test_step_not_initable():
    """Step cant be instantiated"""

    with pytest.raises(TypeError) as exec_info:
        Step()              # pylint: disable=abstract-class-instantiated
    assert "Can't instantiate" in str(exec_info.value)


def test_stepio_not_initable():
    """StepIO cant be instantiated"""

    with pytest.raises(TypeError) as exec_info:
        StepIO('/a/path')    # pylint: disable=abstract-class-instantiated
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
    args = {'--list-langs' : None}

    # act
    step = StepTesseract(path_tiff, args)

    # assert
    assert 'tesseract --list-langs' in step.cmd


def test_step_tesseract_path_out_folder(path_tiff):
    """Tesseract path to write result"""

    # arrange
    args = {'-l' : 'deu', 'alto': None}

    # act
    step = StepTesseract(path_tiff, args=args, path_out_folder="/tmp")

    # assert
    assert '/tmp/500_gray00001_st.xml' in step.path_out


def test_step_tesseract_misses_args(path_tiff):
    """Tesseract path to write result"""

    # act
    with pytest.raises(StepException) as excinfo:
        StepTesseract(path_tiff, args=None, path_out_folder="/tmp")

    # assert
    actual_exc_text = str(excinfo.value)
    assert 'Invalid Dictionary for arguments provided: "None" !' in actual_exc_text


def test_step_tesseract_full_args(path_tiff):
    """Tesseract check cmd from args from following schema:
    'tesseract --dpi 500 <read_path> <out_path> -l <DEFAULT_CHARSET> alto'
    """

    # arrange
    # some args are computed later on
    args = {'--dpi' : 500, '-l': 'frk', 'alto': None}

    # act
    step = StepTesseract(path_tiff, args)
    step.update_cmd()

    # assert
    cmd = f'tesseract {path_tiff} {os.path.splitext(path_tiff)[0]} --dpi 500 -l frk alto'
    assert cmd == step.cmd
    assert step.path_out.endswith('500_gray00001_st.xml')


def test_step_tesseract_different_configurations(path_tiff):
    """Check cmd from args use different lang config"""

    # arrange
    args = {'-l': 'frk_ulbzd1', 'alto': None, 'txt': None}

    # act
    step = StepTesseract(path_tiff, args)
    step.update_cmd()

    # assert
    tesseract_cmd = f'tesseract {path_tiff} {os.path.splitext(path_tiff)[0]} -l frk_ulbzd1 alto txt'
    assert tesseract_cmd == step.cmd


def test_step_copy_alto_back(path_tiff):
    """Move ALTO file back to where we started"""

    # arrange
    target_path = '/tmp/500_gray00001_st.tif'

    # act
    step = StepPostMoveAlto(path_tiff, target_path)
    step.execute()

    # assert
    assert path_tiff == step.path_in
    assert step.path_out == '/tmp/500_gray00001_st.xml'
    assert os.path.exists(step.path_out)


def test_step_replace():
    """unittest replace func"""

    # arrange
    src = './test/resources/500_gray00003.xml'
    dict_chars = {'ſ': 's', 'ic)' : 'ich'}
    step = StepPostReplaceChars(src, dict_chars)
    lines = ['<String ID="string_405" HPOS="831" VPOS="4906" WIDTH="246" HEIGHT="82" WC="0.96" CONTENT="geweſen"/>']
    lines.append('<String ID="string_406" HPOS="1123" VPOS="4904" WIDTH="80" HEIGHT="78" WC="0.95" CONTENT="iſt."/>')
    lines.append('<String ID="string_407" HPOS="1276" VPOS="4903" WIDTH="289" HEIGHT="80" WC="0.96" CONTENT="Beſtätigt"/>')

    # act
    step._replace(lines)

    # assert
    assert len(step.lines_new) == 3
    assert not 'iſt.' in step.lines_new[1]
    assert 'ist.' in step.lines_new[1]
    assert step.must_backup()


@pytest.fixture(name='create_tmp_500_gray')
def fixture_create_tmp_500_gray(tmpdir):
    """create tmp data from file 500_gray00003.xml"""

    path = tmpdir.mkdir("xml").join("input.xml")
    shutil.copyfile('./test/resources/500_gray00003.xml', path)
    return path


def test_replaced_file_written(create_tmp_500_gray):
    """test replaced file written"""

    # arrange
    dict_chars = {'ſ': 's', 'ic)' : 'ich'}
    step = StepPostReplaceChars(str(create_tmp_500_gray), dict_chars)

    # act
    step.execute()

    #assert
    check_handle = open(create_tmp_500_gray, 'r')
    lines = check_handle.readlines()
    for line in lines:
        for (k, _) in dict_chars.items():
            assert k not in line
    check_handle.close()

    assert os.path.exists(os.path.join(os.path.dirname(create_tmp_500_gray),
                                       'input_before_StepPostReplaceChars.xml'))
    assert not os.path.exists(os.path.join(os.path.dirname(create_tmp_500_gray),
                                           'input_before_StepPostReplaceCharsRegex.xml'))


def test_replaced_file_statistics(create_tmp_500_gray):
    """test statistics available"""

    # arrange
    dict_chars = {'ſ': 's', 'ic)' : 'ich'}
    step = StepPostReplaceChars(str(create_tmp_500_gray), dict_chars)

    # act
    step.execute()

    #assert
    expected = ['ſ:392', 'ic):6']
    assert expected == step.get_statistics()
    assert os.path.exists(os.path.join(os.path.dirname(create_tmp_500_gray),
                                       'input_before_StepPostReplaceChars.xml'))


def test_regex_replacements(create_tmp_500_gray):
    """check regex replacements in total"""

    # arrange
    regex_replacements = [RegexReplacement(r'([aeioubcglnt]3[:-]*")', '3', 's')]
    step = StepPostReplaceCharsRegex(str(create_tmp_500_gray), regex_replacements)

    # act
    step.execute()

    # assert
    assert not os.path.exists(os.path.join(os.path.dirname(str(create_tmp_500_gray)),
                                           'input_before_StepPostReplaceChars.xml'))
    with open(str(create_tmp_500_gray)) as test_handle:
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
    assert expected == step.get_statistics()


def test_remove_failed():
    """Test remove failed since file is missing"""

    # arrange
    with pytest.raises(RuntimeError):
        StepPostRemoveFile('qwerrwe.tif', 'tif')


def test_remove_succeeded(path_tiff):
    """Test remove success"""

    # arrange
    path_tmp = './test/resources/tmp_gray00001.tif'
    shutil.copyfile(path_tiff, path_tmp)
    step = StepPostRemoveFile(path_tmp, 'tif')

    # act
    step.execute()

    #assert
    assert step.is_removed()
