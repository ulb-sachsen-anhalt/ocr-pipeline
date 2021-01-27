# -*- coding: utf-8 -*-
"""ULB DD/IT OCR Pipeline Workflow"""

import argparse
import concurrent.futures
import configparser
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


# python process-wrapper
os.environ['OMP_THREAD_LIMIT'] = '1'

MARK_MISSING_ESTM = -1


class OCRPipeline():
    """Wrap configuration"""

    def __init__(self, scandata_path, conf_file=None):
        self.cfg = configparser.ConfigParser()
        self.scandata_path = scandata_path
        if conf_file is None:
            project_dir = os.path.dirname(__file__)
            conf_file = os.path.join(project_dir, 'conf', 'ocr_config.ini')
        read_files = self.cfg.read(conf_file)
        if not read_files:
            raise ValueError('Error: Missing Pipeline-Configuration!')
        self._init_logger()

    def get(self, section, option):
        """Get configured option from section"""

        return self.cfg.get(section, option)

    def scanpath(self):
        """get scandata path"""

        return self.scandata_path

    def _init_logger(self):
        logger_folder = self.cfg.get('pipeline', 'logdir', fallback='/tmp/ocr-pipeline-log')
        right_now = time.strftime('%Y-%m-%d_%H-%M', time.localtime())
        # path exists but cant be written
        if not os.path.exists(logger_folder) or not os.access(logger_folder, os.W_OK):
            logger_folder = '/tmp/ocr-pipeline-log'
            # use default project log path
            # create if not existing
            if not os.path.exists(logger_folder):
                os.makedirs(logger_folder)

        # set scandata path as logfile prefix
        file_prefix = os.path.basename(self.scandata_path)
        # save check if path got trailing slash
        if self.scandata_path.endswith("/"):
            file_prefix = 'ocr'

        self.logfile_name = os.path.join(
            logger_folder, f"{file_prefix}_{right_now}.log")
        conf_logname = {'logname': self.logfile_name}

        # config file location
        project_dir = os.path.dirname(__file__)
        conf_file_location = os.path.join(
            project_dir, 'conf', 'ocr_logger_config.ini')
        logging.config.fileConfig(conf_file_location, defaults=conf_logname)
        logger_name = self.cfg.get('pipeline', 'logger_name')
        self.the_logger = logging.getLogger(logger_name)
        self.the_logger.info("init logging from '%s' at '%s'", str(
            conf_file_location), self.logfile_name)

    def log(self, lvl, message):
        """write messages to log"""

        func = getattr(self.the_logger, lvl, 'info')
        func(message)

    def _write_mark(self, mark):
        if self.scandata_path:
            right_now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            old_label = self.cfg.get('pipeline', 'mark_prev')
            if not old_label:
                self.log(
                    'error', f"Miss preceeding marker, unable to set mark '{mark}'")
            old_marker = os.path.join(self.scandata_path, old_label)
            with open(old_marker, 'a+') as m_file:
                m_file.write(f"\n{right_now} [INFO ] switch to state {mark}")
            os.rename(old_marker, os.path.join(self.scandata_path, mark))

    def mark_fail(self):
        """mark state pipeline failed"""

        self._write_mark('ocr_fail')

    def mark_done(self):
        """Mark state pipeline succeded"""

        self._write_mark('ocr_done')

    def prepare_workdir(self, workdir=None):
        """prepare workdir: create or clear if necessary"""

        workdir_tmp = workdir
        if not workdir_tmp:
            self.log('warning', f"no workdir set, use conf: {workdir_tmp}")
            workdir_tmp = self.cfg.get('pipeline', 'workdir')

        if not os.path.isdir(workdir_tmp):
            if os.access(workdir_tmp, os.W_OK):
                os.makedirs(workdir_tmp)
            else:
                self.log('warning', f"workdir {workdir_tmp} not writable, use tmp dir")
                workdir_tmp = '/tmp/ocr-pipeline-workdir'
                if os.path.exists(workdir_tmp):
                    self._clean_workdir(workdir_tmp)
                os.makedirs(workdir_tmp, exist_ok=True)
        else:
            self._clean_workdir(workdir_tmp)

        return workdir_tmp

    def _clean_workdir(self, the_dir):
        """clear previous work artifacts"""

        self.log('info', f"clean existing workdir '{the_dir}'")
        for file_ in os.listdir(the_dir):
            fpath = os.path.join(the_dir, file_)
            if os.path.isfile(fpath):
                os.unlink(fpath)

    def profile(self, func):
        """profile execution time of provided function"""

        func_start = time.time()
        func()
        func_end = time.time()
        func_delta = func_end - func_start
        label = str(func).split()[4].split('.')[2]
        return f"'{label}' passed in {func_delta:.2f}s"

    def store_estimations(self, estms):
        """Postprocessing of OCR-Quality Estimation Data"""

        valids = [r for r in estms if r[1] != -1]
        invalids = [r for r in estms if r[1] == -1]
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
            self.log(
                'info', f"WTR (Mean) : '{mean}' (1: {b_1}/{n_v}, ... 5: {b_5}/{n_v})")
            end_time = time.strftime('%Y-%m-%d_%H-%M', time.localtime())
            file_name = os.path.basename(self.scandata_path)
            file_path = os.path.join(
                self.scandata_path, f"{file_name}_{end_time}.wtr")
            with open(file_path, 'w') as outfile:
                outfile.write(
                    f"{mean},{b_1},{b_2},{b_3},{b_4},{b_5},{len(estms)},{n_i}\n")
                for s in sorteds:
                    outfile.write(
                        f"{s[0]},{s[1]:.3f},{s[2]},{s[3]},{s[4]},{s[5]},{s[6]},{s[7]}\n")
                outfile.write("\n")
                return file_path

    def get_images_sorted(self):
        """get all images tif|jpg|png as sorted list"""

        img_exts = [self.cfg.get('pipeline', 'image_ext')]
        if "," in img_exts[0]:
            img_exts = img_exts[0].split(",")

        def _f(path):
            for img_ext in img_exts:
                if str(path).endswith(img_ext):
                    return True

        image_paths = [str(i) for i in pathlib.Path(
            self.scandata_path).iterdir() if _f(i)]
        return sorted(image_paths)


def _execute_pipeline(start_path):
    next_in = start_path
    step_label = 'start'
    image_name = os.path.basename(start_path)

    try:
        # forward to tesseract
        args = {'--dpi': DPI, '-l': MODEL_CONFIG, 'alto': None}
        step_tesseract = StepTesseract(next_in, args, path_out_folder=WORK_DIR)
        step_label = type(step_tesseract).__name__
        step_tesseract.update_cmd()
        pipeline.log(
            'debug', f"[{image_name}] tesseract args {step_tesseract.cmd}")
        result = pipeline.profile(step_tesseract.execute)
        pipeline.log('debug', f"[{image_name}] step {result}")
        next_in = step_tesseract.path_out

        # post correct ALTO data
        stats = []
        dict2 = {'ic)': 'ich', 's&lt;': 'sc', '&lt;': 'c'}
        must_backup = pipeline.get('step_replace', 'must_backup')
        step_replace = StepPostReplaceChars(
            next_in, dict2, must_backup=must_backup)
        step_label = type(step_replace).__name__
        step_replace.execute()
        replacements = step_replace.get_statistics()
        if replacements:
            stats += replacements
        next_in = step_replace.path_out
        replace_trailing_three = RegexReplacement(
            r'([aeioubcglnt]3[:-]*")', '3', 's')
        regex_replacements = [replace_trailing_three]
        step_regex = StepPostReplaceCharsRegex(
            next_in, regex_replacements, must_backup=must_backup)
        step_label = type(step_regex).__name__
        step_regex.execute()
        regexs = step_regex.get_statistics()
        if regexs:
            stats += regexs
        if stats:
            pipeline.log(
                'debug', f"[{image_name}] replace >>[{', '.join(stats)}]<<")
        next_in = step_replace.path_out

        # estimate OCR quality
        result = None
        estm_required = str(pipeline.get('step_language_tool', 'active'))
        if estm_required.upper() == 'TRUE':
            lturl = pipeline.get('step_language_tool', 'url')
            ltlang = pipeline.get('step_language_tool', 'language')
            if not lturl or not ltlang:
                pipeline.log(
                    'warning', f"[{image_name}] invalid {lturl} or {ltlang}, skipping")
            else:
                ltrules = pipeline.get('step_language_tool', 'enabled_rules')
                step_estm = StepEstimateOCR(next_in, lturl, ltlang, ltrules)
                step_label = type(step_estm).__name__
                if step_estm.is_available():
                    try:
                        result = pipeline.profile(step_estm.execute)
                        pipeline.log('debug', f"[{image_name}] step {result}")
                        result = step_estm.get()
                    except StepException as exc:
                        pipeline.log(
                            'warning', f"Error at '{step_label}: {exc}")

        # move ALTO Data
        step_move_alto = StepPostMoveAlto(next_in, start_path)
        step_label = type(step_move_alto).__name__
        step_move_alto.execute()

        if result is not None:
            (wtr, nws, nes, nin, nwraps, nss, nout) = result
            l_e = f"[{image_name}] WTR '{wtr}' ({nes}/{nws}, {nin}=>[{nwraps},{nss}]=>{nout})"
            pipeline.log('info', l_e)
            return (image_name, wtr, nws, nes, nin, nwraps, nss, nout)

        # if estimation result missing, just return image name and missing mark "-1"
        return (image_name, MARK_MISSING_ESTM)

    except StepException as exc:
        pipeline.log('error', f"[{start_path}] {step_label}: {exc}")
        sys.exit(1)
    except OSError as exc:
        pipeline.log('error', f"[{start_path}] {step_label}: {exc}")
        sys.exit(1)


# main entry point
if __name__ == '__main__':
    APP_ARGUMENTS = argparse.ArgumentParser()
    APP_ARGUMENTS.add_argument(
        "-s", "--scandata", required=True, help="path to scandata")
    APP_ARGUMENTS.add_argument(
        "-w", "--workdir", required=False, help="path to workdir")
    APP_ARGUMENTS.add_argument(
        "-m", "--models", required=False, help="tesseract model config")
    APP_ARGUMENTS.add_argument(
        "-d", "--dpi", required=False, help="DPI for pipeline")
    APP_ARGUMENTS.add_argument(
        "-e", "--executors", required=False, help="N of Pipeline Executors")
    ARGS = vars(APP_ARGUMENTS.parse_args())

    SCANDATA_PATH = ARGS["scandata"]
    if not os.path.isdir(SCANDATA_PATH):
        print(
            f"[ERROR] scandata path '{SCANDATA_PATH}' invalid!", file=sys.stderr)
        sys.exit(1)

    # create ocr pipeline wrapper instance
    pipeline = OCRPipeline(SCANDATA_PATH)

    # setup workdir
    WORK_DIR = pipeline.prepare_workdir(ARGS["workdir"])

    #
    # setup some more pipeline parameters
    #
    # resolution
    if ARGS['dpi'] is not None:
        DPI = ARGS['dpi']
    else:
        DPI = pipeline.get('pipeline', 'dpi')
    # size of process pool
    if ARGS['executors'] is not None:
        WORKER = int(ARGS['executors'])
    else:
        WORKER = int(pipeline.get('pipeline', 'executors'))
    # special model configuration
    MODEL_CONFIG = ARGS["models"]
    if not MODEL_CONFIG:
        MODEL_CONFIG = pipeline.get('pipeline', 'model_configs')
        pipeline.log(
            'warning', f"no model config set, use configuration '{MODEL_CONFIG}'")

    # read and sort image files
    IMAGE_PATHS = pipeline.get_images_sorted()

    # debugging output
    START_MSG_1 = f"ocr {len(IMAGE_PATHS)} scans (dpi:{DPI}) at '{SCANDATA_PATH}' in '{WORK_DIR}'"
    START_MSG_2 = f"use '{WORKER}' execs with conf '{MODEL_CONFIG}'"
    pipeline.log('info', START_MSG_1)
    pipeline.log('info', START_MSG_2)

    START_TS = time.time()
    # perform sequential part of pipeline with parallel processing
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=WORKER) as executor:
            ESTIMATIONS = list(executor.map(_execute_pipeline, IMAGE_PATHS))
            estimations = [r for r in ESTIMATIONS if r[1] > MARK_MISSING_ESTM]
            if estimations:
                pipeline.store_estimations(estimations)
            else:
                pipeline.log(
                    'info', "no ocr estimation data available, no wtr-data written")

    except OSError as exc:
        pipeline.log('error', str(exc))
        raise OSError from exc

    DELTA_TS = (time.time()) - START_TS
    MSG_RT = f'{DELTA_TS:.2f} sec ({math.floor(DELTA_TS/60)}min {math.floor(DELTA_TS % 60)}sec)'
    END_TS = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    pipeline.log('info', f"Pipeline finished at '{END_TS}' ({MSG_RT})")
    pipeline.mark_done()
