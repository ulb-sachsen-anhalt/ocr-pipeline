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
import tempfile
import time

# pylint: disable=unused-import
# import statement *is_REALLY* necessary
# for global clazz loading
from lib.ocr_step import (
    StepPostReplaceChars,
    StepException,
    StepIO,
    StepIOExtern,
    StepTesseract,
    StepPostReplaceCharsRegex,
    StepPostMoveAlto,
    StepEstimateOCR,
    StepPostprocessALTO
)


# python process-wrapper
os.environ['OMP_THREAD_LIMIT'] = '1'

MARK_MISSING_ESTM = -1

DEFAULT_PATH_CONFIG = 'conf/ocr_config.ini'


class OCRPipeline():
    """Control pipeline workflow"""

    def __init__(self, scandata_path, conf_file=None, log_dir=None):
        self.cfg = configparser.ConfigParser()
        _path = scandata_path
        if _path.endswith('/'):
            _path = _path[0:-1]
        self.scandata_path = _path
        if conf_file is None:
            project_dir = os.path.dirname(__file__)
            conf_file = os.path.join(project_dir, DEFAULT_PATH_CONFIG)
        read_files = self.cfg.read(conf_file)
        self.tesseract_args = {}
        if not read_files:
            raise ValueError('Error: Missing Pipeline-Configuration!')
        if log_dir:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            self.cfg['pipeline']['logdir'] = log_dir
        self._init_logger()
        self.prepare_workdir()

    def get(self, section, option):
        """Get configured option from section"""

        return self.cfg.get(section, option)

    def merge_args(self, arguments):
        """Merge configuration with CLI arguments"""

        if 'workdir' in arguments and arguments['workdir']:
            self.cfg.set('pipeline', 'workdir', arguments["workdir"])
        if 'executors' in arguments and arguments['executors']:
            self.cfg['pipeline']['executors'] = arguments['executors']
        # handle tesseract args
        sects_tess = self._get_tesseract_section()
        if len(sects_tess) > 0:
            sect_tess = sects_tess[0]
            if 'models' in arguments and arguments['models']:
                sect_tess['model_configs'] = arguments['models']
            if 'extra' in arguments and arguments['extra']:
                # ensure that empty single quotes aren't propagated further
                xtra_args = [e for e in arguments['extra'] if e.strip("'")]
                if xtra_args:
                    sect_tess['extra'] = ''.join(arguments['extra'])
            if 'tesseract_bin' in arguments and arguments['tesseract_bin']:
                sect_tess['tesseract_bin'] = arguments['tesseract_bin']

    def _get_tesseract_section(self):
        return [self.cfg[s]
                for s in self.cfg.sections()
                for k, v in self.cfg[s].items()
                if k == 'type' and 'esseract' in str(v)]

    def get_steps(self):
        """
        Create all configured steps each time again
        labeled like 'step_01', step_02' and so forth
        to ensure their sequence
        """

        steps = []
        step_configs = [
            s for s in self.cfg.sections() if s.startswith('step_')]
        sorted_steps = sorted(step_configs, key=lambda s: int(s.split('_')[1]))
        for step in sorted_steps:
            the_type = self.cfg.get(step, 'type')
            the_keys = self.cfg[step].keys()
            the_kwargs = {k: self.cfg[step][k] for k in the_keys}
            the_step = globals()[the_type](the_kwargs)
            steps.append(the_step)
        return steps

    def _init_logger(self):
        fallback_logdir = os.path.join(
            tempfile.gettempdir(), 'ocr-pipeline-log')
        logger_folder = self.cfg.get('pipeline', 'logdir')
        right_now = time.strftime('%Y-%m-%d_%H-%M', time.localtime())
        # path exists but cant be written
        if not os.path.exists(logger_folder) or not os.access(logger_folder, os.W_OK):
            logger_folder = fallback_logdir
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
            workdir_tmp = self.cfg.get('pipeline', 'workdir')
            self.log('warning', f"no workdir set, using '{workdir_tmp}'")

        if not os.path.isdir(workdir_tmp):
            if os.access(workdir_tmp, os.W_OK):
                os.makedirs(workdir_tmp)
            else:
                self.log(
                    'warning', f"workdir {workdir_tmp} not writable, use tmp dir")
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

    def store_estimations(self, estms):
        """Postprocessing of OCR-Quality Estimation Data"""

        valids = [r for r in estms if r[1] != -1]
        invalids = [r for r in estms if r[1] == -1]
        sorteds = sorted(valids, key=lambda r: r[1])
        aggregations = StepEstimateOCR.analyze(sorteds)
        end_time = time.strftime('%Y-%m-%d_%H-%M', time.localtime())
        file_name = os.path.basename(self.scandata_path)
        file_path = os.path.join(
            self.scandata_path, f"{file_name}_{end_time}.wtr")
        self.log('info', f"store mean '{aggregations[0]}' in '{file_path}'")
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
            with open(file_path, 'w') as outfile:
                outfile.write(
                    f"{mean},{b_1},{b_2},{b_3},{b_4},{b_5},{len(estms)},{n_i}\n")
                for s in sorteds:
                    outfile.write(
                        f"{s[0]},{s[1]:.3f},{s[2]},{s[3]},{s[4]},{s[5]},{s[6]},{s[7]}\n")
                outfile.write("\n")
                return file_path

    def get_input_sorted(self, recursive=False):
        """get input data as sorted list, opt recursive"""

        exts = [self.cfg.get('pipeline', 'file_ext')]
        if "," in exts[0]:
            exts = exts[0].split(",")

        def _f(path):
            for file_ext in exts:
                if str(path).endswith(file_ext):
                    return True
            return False

        paths = []
        if not recursive:
            paths = [str(p)
                     for p in pathlib.Path(self.scandata_path).iterdir()
                     if _f(p)]
        else:
            paths = [os.path.join(curr,f)
                     for curr, _, files in os.walk(self.scandata_path)
                     for f in files
                     if _f(f)]
        return sorted(paths)


def profile(func):
    """profile execution time of provided function"""

    func_start = time.time()
    func()
    func_end = time.time()
    func_delta = func_end - func_start
    label = str(func).split()[4].split('.')[2]
    return f"'{label}' passed in {func_delta:.2f}s"


def _execute_pipeline(*args):
    number = args[0][0]
    start_path = args[0][1]
    file_nr = f"{number:04d}/{len(INPUT_PATHS):04d}"
    next_in = start_path
    step_label = 'start'
    file_name = os.path.basename(start_path)
    outcome = (file_name, MARK_MISSING_ESTM)

    try:
        the_steps = pipeline.get_steps()
        pipeline.log(
            'info', f"[{file_name}] [{file_nr}] start pipeline with {the_steps}")

        # for step in STEPS:
        for step in the_steps:
            step.path_in = next_in
            if isinstance(step, StepIOExtern):
                pipeline.log('debug', f"[{file_name}] {step.cmd}")

            # the actual execution
            result = profile(step.execute)

            # log current step
            if hasattr(step, 'statistics') and len(step.statistics) > 0:
                statistics = step.statistics
                pipeline.log(
                    'debug', f"[{file_name}] statistics: {statistics}")
                if result and isinstance(step, StepEstimateOCR):
                    outcome = (file_name,) + statistics
            pipeline.log('info', f"[{file_name}] step {result}")

            # prepare next step
            if hasattr(step, 'path_next') and step.path_next is not None:
                pipeline.log('debug', f'{step}.path_next: {step.path_next}')
                next_in = step.path_next

        pipeline.log(
            'info', f"[{file_name}] [{file_nr}] done pipeline with {len(the_steps)} steps")
        return outcome

    except StepException as exc:
        pipeline.log('error', f"[{start_path}] {step_label}: {exc}")
        sys.exit(1)
    except OSError as exc:
        pipeline.log('error', f"[{start_path}] {step_label}: {exc}")
        sys.exit(1)


# main entry point
if __name__ == '__main__':
    APP_ARGUMENTS = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter)
    APP_ARGUMENTS.add_argument(
        "scandata",
        help="path to scandata dir")
    APP_ARGUMENTS.add_argument(
        "-r",
        "--recursive",
        required=False,
        default=False,
        action='store_true',
        help="iterate recursive from scandata path top-down")
    APP_ARGUMENTS.add_argument(
        "-c",
        "--config",
        required=False,
        help="path to config file",
        default=DEFAULT_PATH_CONFIG)
    APP_ARGUMENTS.add_argument(
        "-w",
        "--workdir",
        required=False,
        help="path to workdir")
    APP_ARGUMENTS.add_argument(
        "-e",
        "--executors",
        required=False,
        help="Number of Executors")
    APP_ARGUMENTS.add_argument(
        "-m",
        "--models",
        required=False,
        help="Tesseract model configuration")
    APP_ARGUMENTS.add_argument(
        "-x",
        "--extra",
        required=False,
        nargs='+',
        help='''\
        Pass args direct to tesseract
        Use Pairwise and repeatable
        i.e. like "--dpi <val> --psm <val>"
        ''')
    ARGS = vars(APP_ARGUMENTS.parse_args())

    SCANDATA_PATH = ARGS["scandata"]
    if not os.path.isdir(SCANDATA_PATH):
        print(
            f"[ERROR] scandata path '{SCANDATA_PATH}' invalid!", file=sys.stderr)
        sys.exit(1)
    CONFIG = ARGS.get('config', DEFAULT_PATH_CONFIG)

    # create ocr pipeline wrapper instance
    pipeline = OCRPipeline(SCANDATA_PATH, CONFIG)

    # update pipeline configuration with cli args
    pipeline.merge_args(ARGS)
    EXECUTORS = pipeline.cfg.getint('pipeline', 'executors')
    INPUT_PATHS = pipeline.get_input_sorted(ARGS['recursive'])
    INPUT_NUMBERED = [(i, img)
                      for i, img in enumerate(INPUT_PATHS, start=1)]
    START_TS = time.time()

    # perform sequential part of pipeline with parallel processing
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=EXECUTORS) as executor:
            RESULTS = list(executor.map(_execute_pipeline, INPUT_NUMBERED))
            pipeline.log('debug', f"having '{len(RESULTS)}' workflow results")
            estimations = [r for r in RESULTS if r[1] > MARK_MISSING_ESTM]
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
