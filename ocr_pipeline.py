# -*- coding: utf-8 -*-
"""ULB DD/IT OCR Pipeline Workflow"""

import argparse
import concurrent.futures
import glob
import logging
import logging.config
import math
import os
import sys
import traceback
import time

from lib.ocr_step import (
    StepTesseract,
    StepPostMoveAlto,
    StepPostReplaceChars,
    RegexReplacement,
    StepPostReplaceCharsRegex
)


# regarding python process-wrapper
os.environ['OMP_THREAD_LIMIT'] = '1'

# fallback: where to store pipeline artifacts
DEFAULT_WORK_DIR = '/tmp/ocr-pipeline'

# fallback: resolution
DEFAULT_DPI = '470'

# fallback: executors for process pool
DEFAULT_WORKER = 4

# fallback: tesseract model config to use
# frk = Fraktura
# deu_frak = Deutsch-Fraktur
DEFAULT_MODEL = 'frk'

# stage before ocr stage
PREVIOUS_STAGE = 'meta_done'

# provide THE_LOGGER
LOG_FOLDER = '/opt/ulb/ocr/log'
LOGGER_NAME = 'ocr_pipeline'
FORMATTER = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')


class OCRLog:
    """Manage Logger"""

    instance = None

    class _TheSecretLogger:

        def __init__(self, logger_folder, fallback):
            datetime_stamp = time.strftime('%Y-%m-%d_%H-%M', time.localtime())

            # safety fallbacks if path not existing
            if not os.path.exists(logger_folder):
                logger_folder = os.path.join(logger_folder, 'log')
            # path exists but cant be written
            if os.path.exists(logger_folder) and not os.access(logger_folder, os.W_OK):
                logger_folder = os.path.join(fallback, 'log')
                # create default tmp path if not existing
                if not os.path.exists(logger_folder):
                    os.makedirs(logger_folder)

            # set film nr as logfile prefix
            file_prefix = os.path.basename(SCANDATA_PATH)
            if SCANDATA_PATH.endswith("/"):
                file_prefix = 'ocr'

            self.logfile_name = os.path.join(logger_folder, file_prefix+'_'+datetime_stamp+'.log')
            print("[DEBUG] creating logfile '{}'".format(self.logfile_name))
            conf_logname = {'logname' : self.logfile_name}
            logging.config.fileConfig('ocr_logger_config.ini', defaults=conf_logname)
            logging.lastResort = None
            self.the_logger = logging.getLogger(LOGGER_NAME)


    @classmethod
    def get(cls, logger_folder, fallback='/tmp/ocr-pipeline') -> logging.Logger:
        """return Logger Singleton"""

        if not cls.instance:
            cls.instance = OCRLog._TheSecretLogger(logger_folder, fallback).the_logger
        return cls.instance


def _clean_dir(the_dir):
    THE_LOGGER.info('clean workdir \'%s\'', the_dir)
    if os.path.isdir(the_dir):
        for file_ in os.listdir(the_dir):
            file_path = os.path.join(the_dir, file_)
            if os.path.isfile(file_path):
                os.unlink(file_path)
    else:
        THE_LOGGER.error('invalid workdir \'%s\' specified', the_dir)
        sys.exit(3)


def _profile(func, img_path):
    func_start = time.time()
    func()
    func_end = time.time()
    func_delta = func_end - func_start
    label = str(func).split()[4].split('.')[2]
    image_name = os.path.basename(img_path)
    THE_LOGGER.info('[{}] step "{}" passed in {:.2f} s'.format(image_name, label, func_delta))


def _execute_pipeline(start_path):
    next_in = start_path
    scan_folder = os.path.dirname(next_in)
    step_label = 'start'
    pipeline_start = time.time()
    image_name = os.path.basename(start_path)

    try:
        # forward to tesseract
        args = {'--dpi' : DPI, '-l': MODEL_CONFIG, 'alto': None}
        step_tesseract = StepTesseract(next_in, args, path_out_folder=WORK_DIR)
        step_label = type(step_tesseract).__name__
        step_tesseract.update_cmd()
        THE_LOGGER.debug('[{}] tesseract args {}'.format(image_name, step_tesseract.cmd))
        _profile(step_tesseract.execute, start_path)
        next_in = step_tesseract.path_out

        # post correct ALTO data
        stats = []
        dict2 = {'ic)' : 'ich', 's&lt;' : 'sc', '&lt;':'c'}
        step_replace = StepPostReplaceChars(next_in, dict2)
        step_label = type(step_replace).__name__
        step_replace.execute()
        replacements = step_replace.get_statistics()
        if replacements:
            stats += replacements
        next_in = step_replace.path_out
        replace_trailing_three = RegexReplacement(r'([aeioubcglnt]3[:-]*")', '3', 's')
        regex_replacements = [replace_trailing_three]
        step_regex = StepPostReplaceCharsRegex(next_in, regex_replacements)
        step_label = type(step_regex).__name__
        step_regex.execute()
        regexs = step_regex.get_statistics()
        if regexs:
            stats += regexs
        if stats:
            THE_LOGGER.info('[{}] replace >>[{}]<<'.format(image_name, ', '.join(stats)))
        next_in = step_replace.path_out

        # move ALTO Data
        step_move_alto = StepPostMoveAlto(next_in, start_path)
        step_label = type(step_move_alto).__name__
        step_move_alto.execute()

    except OSError as exc:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout)
        THE_LOGGER.error('[{}] FAIL OCR_Pipeline in {} at {} with {}'.format(start_path,
                                                                             scan_folder,
                                                                             step_label, exc))
        sys.exit(1)

    # delta time
    pipeline_end = time.time()
    pipeline_delta = pipeline_end - pipeline_start
    THE_LOGGER.info('[{}] passed pipeline in {:.2f}s'.format(image_name, pipeline_delta))

    # final return
    return start_path


# main entry point
if __name__ == '__main__':
    APP_ARGUMENTS = argparse.ArgumentParser()
    APP_ARGUMENTS.add_argument("-s", "--scandata", required=True, help="path to scandata")
    APP_ARGUMENTS.add_argument("-w", "--workdir", required=True, help="path to workdir")
    APP_ARGUMENTS.add_argument("-e", "--executors", required=True, help="size of executorpool")
    APP_ARGUMENTS.add_argument("-d", "--dpi", required=False, help="resolution in dpi")
    APP_ARGUMENTS.add_argument("-m", "--models", required=False, help="tesseract model config")
    ARGS = vars(APP_ARGUMENTS.parse_args())

    SCANDATA_PATH = ARGS["scandata"]
    if not os.path.isdir(SCANDATA_PATH):
        print('scandata path \'{}\' not accessible'.format(SCANDATA_PATH), file=sys.stderr)
        sys.exit(2)
    THE_LOGGER = OCRLog.get(LOG_FOLDER, DEFAULT_WORK_DIR)

    WORK_DIR = ARGS["workdir"]
    if not WORK_DIR:
        WORK_DIR = DEFAULT_WORK_DIR
        THE_LOGGER.warning('no workdir: fallback to %s', WORK_DIR)
    if not os.path.isdir(WORK_DIR):
        THE_LOGGER.warning('invalid workdir %s: fallback to %s', WORK_DIR, DEFAULT_WORK_DIR)
        WORK_DIR = '/tmp/ocr-tesseract'
    WORKER = int(ARGS["executors"])
    if not WORKER:
        THE_LOGGER.warning('no executor poolsize set: fallback to %s', DEFAULT_WORKER)
        WORKER = DEFAULT_WORKER
    DPI = ARGS["dpi"]
    if not DPI:
        DPI = DEFAULT_DPI
    MODEL_CONFIG = ARGS["models"]
    if not MODEL_CONFIG:
        THE_LOGGER.warning('no model configuration was set: fallback to %s', DEFAULT_MODEL)
        MODEL_CONFIG = DEFAULT_MODEL

    # read and sort image files
    IMAGE_PATHS = glob.glob(SCANDATA_PATH+"/*.tif")
    IMAGE_PATHS = sorted(IMAGE_PATHS)

    # debugging output
    START_MSG_1 = f"ocr {len(IMAGE_PATHS)} scans (dpi:{DPI}) at '{SCANDATA_PATH}' in '{WORK_DIR}'"
    START_MSG_2 = f"use '{WORKER}' execs with conf '{MODEL_CONFIG}'"
    print(START_MSG_1 + START_MSG_2)
    THE_LOGGER.info(START_MSG_1)
    THE_LOGGER.info(START_MSG_2)

    # wipe possible relicts
    _clean_dir(WORK_DIR)


    START_TS = time.time()
    # perform sequential part of pipeline with parallel processing
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=WORKER) as executor:
            executor.map(_execute_pipeline, IMAGE_PATHS)
    except OSError as exc:
        THE_LOGGER.error(exc)
        THE_LOGGER.error('unable to proceed, shut down')
        raise OSError(exc)

    DELTA_TS = (time.time()) - START_TS
    MSG_RT = f'{DELTA_TS:.2f} sec ({math.floor(DELTA_TS/60)}min {math.floor(DELTA_TS % 60)}sec)'
    END_TS = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    THE_LOGGER.info(f'end pipeline run "{END_TS}": {MSG_RT}')
    # exchange process state marker - set 'done' at last
    OLD_MARKER = os.path.join(SCANDATA_PATH, 'ocr_busy')
    MARKER_FHANDLE = open(OLD_MARKER, 'a+')
    MARKER_FHANDLE.write('\nswitch state to "ocr_done" in '+SCANDATA_PATH+' at ' + END_TS)
    MARKER_FHANDLE.close()
    os.rename(OLD_MARKER, os.path.join(SCANDATA_PATH, 'ocr_done'))
