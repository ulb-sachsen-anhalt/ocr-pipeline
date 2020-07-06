# -*- coding: utf-8 -*-
"""ULB DD/IT OCR Pipeline Workflow"""

import argparse
import concurrent.futures
import logging
import logging.config
import math
import os
import pathlib
import sys
import time

from lib.ocr_step import (
    StepTesseract,
    StepPostMoveAlto,
    StepPostReplaceChars,
    RegexReplacement,
    StepPostReplaceCharsRegex,
    StepEstimateOCR,
    StepException
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
# frk = Fraktur
# deu_frak = Deutsch-Fraktur
DEFAULT_MODEL = 'frk'

# stage before ocr stage
PREVIOUS_STAGE = 'meta_done'

# provide THE_LOGGER
TIME_STAMP = time.strftime('%Y-%m-%d_%H-%M', time.localtime())
LOG_FOLDER = '/opt/ulb/ocr/logdir'
LOGGER_NAME = 'ocr_pipeline'
#FORMATTER = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')


class OCRLog:
    """Manage Logger"""

    instance = None

    class _TheSecretLogger:

        def __init__(self, logger_folder, fallback):

            # safety fallbacks if path not existing
            if not os.path.exists(logger_folder):
                logger_folder = os.path.join(logger_folder)
            # path exists but cant be written
            if os.path.exists(logger_folder) and not os.access(logger_folder, os.W_OK):
                logger_folder = os.path.join(fallback, 'log')
                # create default tmp path if not existing
                if not os.path.exists(logger_folder):
                    os.makedirs(logger_folder)

            # set scandata path as logfile prefix
            file_prefix = os.path.basename(SCANDATA_PATH)
            if SCANDATA_PATH.endswith("/"):
                file_prefix = 'ocr'

            self.logfile_name = os.path.join(logger_folder, file_prefix+'_'+TIME_STAMP+'.log')
            print(f"[DEBUG] creating logfile '{self.logfile_name}'")
            conf_logname = {'logname' : self.logfile_name}
            logging.config.fileConfig('ocr_logger_config.ini', defaults=conf_logname)
            self.the_logger = logging.getLogger(LOGGER_NAME)


    @classmethod
    def get(cls, logger_folder, fallback='/tmp/ocr-pipeline') -> logging.Logger:
        """return Logger Singleton"""

        if not cls.instance:
            cls.instance = OCRLog._TheSecretLogger(logger_folder, fallback).the_logger
        return cls.instance


def _clean_dir(the_dir):
    THE_LOGGER.info(f"clean workdir '{the_dir}'")
    if os.path.isdir(the_dir):
        for file_ in os.listdir(the_dir):
            fpath = os.path.join(the_dir, file_)
            if os.path.isfile(fpath):
                os.unlink(fpath)
    else:
        THE_LOGGER.error(f"invalid workdir '{the_dir}' specified")
        sys.exit(3)


def _profile(func, img_path):
    func_start = time.time()
    func()
    func_end = time.time()
    func_delta = func_end - func_start
    label = str(func).split()[4].split('.')[2]
    image_name = os.path.basename(img_path)
    THE_LOGGER.debug(f"[{image_name}] step '{label}' passed in {func_delta:.2f}s")


def _execute_pipeline(start_path):
    next_in = start_path
    step_label = 'start'
    pipeline_start = time.time()
    image_name = os.path.basename(start_path)

    try:
        # forward to tesseract
        args = {'--dpi' : DPI, '-l': MODEL_CONFIG, 'alto': None}
        step_tesseract = StepTesseract(next_in, args, path_out_folder=WORK_DIR)
        step_label = type(step_tesseract).__name__
        step_tesseract.update_cmd()
        THE_LOGGER.debug(f"[{image_name}] tesseract args {step_tesseract.cmd}'")
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
            THE_LOGGER.info(f"[{image_name}] replace >>[{', '.join(stats)}]<<")
        next_in = step_replace.path_out

        # estimate OCR quality
        result = None
        step_estm = StepEstimateOCR(next_in, 'http://localhost:8010/v2/check')
        step_label = type(step_estm).__name__
        if step_estm.is_available():
            try:
                _profile(step_estm.execute, start_path)
                result = step_estm.get()
                (wtr, nws, nes, nin, nwraps, nss, nout) = result
                l_e = f"[{image_name}] WTR '{wtr}' ({nes}/{nws}, {nin}=>{nwraps}brk=>{nss}shr=>{nout})"
                THE_LOGGER.info(l_e)
            except StepException as exc:
                THE_LOGGER.warn(f"Error at '{step_label}: {exc}")

        # move ALTO Data
        step_move_alto = StepPostMoveAlto(next_in, start_path)
        step_label = type(step_move_alto).__name__
        step_move_alto.execute()

        if result is not None:
            return (image_name, wtr, nws, nes, nin, nwraps, nss, nout)
        else:
            return (image_name, -1)

    except StepException as exc:
        THE_LOGGER.error(f"[{start_path}] {step_label}: {exc}")
    except OSError as exc:
        THE_LOGGER.error(f"[{start_path}] {step_label}: {exc}")
        sys.exit(1)
    except:
        THE_LOGGER.error(f"[{start_path}] {step_label}: {sys.exc_info()}")
        sys.exit(1)

    # delta time
    pipeline_end = time.time()
    pipeline_delta = pipeline_end - pipeline_start
    THE_LOGGER.info(f"[{image_name}] passed pipeline in {pipeline_delta:.2f}s")

    # final return in case of exceptions or errors
    return (image_name, -1)


def _postprocess(estimations, file_path):
    """Postprocessing of OCR-Quality Estimation Data"""

    valids = [r for r in estimations if r[1] != -1]
    invalids = [r for r in estimations if r[1] == -1]
    sorteds = sorted(valids, key=lambda r: r[1])
    aggregations = StepEstimateOCR.analyze(sorteds)
    if aggregations:
        (mean, bins) = aggregations
        b_1 = len(bins[0])
        b_2 = len(bins[1])
        b_3 = len(bins[2])
        b_4 = len(bins[3])
        b_5 = len(bins[4])
        n_v = len(valids)
        n_i = len(invalids)
        THE_LOGGER.info(f"WTR (Mean) : '{mean}' (1: {b_1}/{n_v}, ... 5: {b_5}/{n_v})")
        with open(file_path, 'w') as outfile:
            outfile.write(f"{mean},{b_1},{b_2},{b_3},{b_4},{b_5},{len(estimations)},{n_i}\n")
            for s in sorteds:
                outfile.write(f"{s[0]},{s[1]:.3f},{s[2]},{s[3]},{s[4]},{s[5]},{s[6]},{s[7]}\n")
            outfile.write("\n")


# main entry point
if __name__ == '__main__':
    APP_ARGUMENTS = argparse.ArgumentParser()
    APP_ARGUMENTS.add_argument("-s", "--scandata", required=True, help="path to scandata")
    APP_ARGUMENTS.add_argument("-w", "--workdir", required=True, help="path to workdir")
    APP_ARGUMENTS.add_argument("-e", "--executors", required=False, help="size of executorpool")
    APP_ARGUMENTS.add_argument("-d", "--dpi", required=False, help="resolution in dpi")
    APP_ARGUMENTS.add_argument("-m", "--models", required=False, help="tesseract model config")
    ARGS = vars(APP_ARGUMENTS.parse_args())

    SCANDATA_PATH = ARGS["scandata"]
    if not os.path.isdir(SCANDATA_PATH):
        print(f"[ERROR] scandata path '{SCANDATA_PATH}' invalid!", file=sys.stderr)
        sys.exit(2)
    THE_LOGGER = OCRLog.get(LOG_FOLDER, DEFAULT_WORK_DIR)

    WORK_DIR = ARGS["workdir"]
    if not WORK_DIR:
        WORK_DIR = DEFAULT_WORK_DIR
        THE_LOGGER.warning(f"workdir not set, fallback to {WORK_DIR}")
    if not os.path.isdir(WORK_DIR):
        THE_LOGGER.warning(f"workdir invalid '{WORK_DIR}', fallback to '{DEFAULT_WORK_DIR}'")
        WORK_DIR = '/tmp/ocr-tesseract'
    EXECS = ARGS["executors"]
    if not EXECS:
        THE_LOGGER.warning(f"number of executors not set, fallback to '{DEFAULT_WORKER}'")
        WORKER = DEFAULT_WORKER
    else:
        WORKER = int(EXECS)
    DPI = ARGS["dpi"]
    if not DPI:
        DPI = DEFAULT_DPI
    MODEL_CONFIG = ARGS["models"]
    if not MODEL_CONFIG:
        THE_LOGGER.warning(f"Tesseract model config not set, fallback to '{DEFAULT_MODEL}'")
        MODEL_CONFIG = DEFAULT_MODEL

    # read and sort image files: tif|jpg|png
    _f = lambda p: str(p).endswith('.tif') or str(p).endswith('.jpg') or str(p).endswith('.png')
    p = pathlib.Path(SCANDATA_PATH)
    IMAGE_PATHS = [str(i) for i in p.iterdir() if _f(i)]
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
            ESTIMATIONS = list(executor.map(_execute_pipeline, IMAGE_PATHS))
            estimations = [r for r in ESTIMATIONS if r[1] > -1]
            if estimations:
                THE_LOGGER.info("start postprocessing ocr estimation data")
                END_TIME = time.strftime('%Y-%m-%d_%H-%M', time.localtime())
                FILE_NAME = os.path.basename(SCANDATA_PATH)
                FILE_PATH = os.path.join(SCANDATA_PATH, FILE_NAME + '_' + END_TIME + '.wtr')
                _postprocess(estimations, FILE_PATH)
            else:
                THE_LOGGER.info("no ocr estimation data for postprocessing available, no data written")

    except OSError as exc:
        THE_LOGGER.error(exc)
        THE_LOGGER.error('unable to proceed, shut down')
        raise OSError(exc)

    DELTA_TS = (time.time()) - START_TS
    MSG_RT = f'{DELTA_TS:.2f} sec ({math.floor(DELTA_TS/60)}min {math.floor(DELTA_TS % 60)}sec)'
    END_TS = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    THE_LOGGER.info(f"Pipeline finished at '{END_TS}' ({MSG_RT})")

    # exchange process state marker - set 'done' at last
    OLD_MARKER = os.path.join(SCANDATA_PATH, 'ocr_busy')
    with open(OLD_MARKER, 'a+') as marker_file:
        marker_file.write('\nswitch state to "ocr_done" in '+SCANDATA_PATH+' at ' + END_TS)

    # set new marker label
    os.rename(OLD_MARKER, os.path.join(SCANDATA_PATH, 'ocr_done'))
