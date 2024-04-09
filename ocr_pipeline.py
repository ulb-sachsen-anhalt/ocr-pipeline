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
DEFAULT_MARK_BUSY = 'ocr_busy'
DEFAULT_MARK_FAIL = 'ocr_fail'
DEFAULT_MARK_DONE = 'ocr_done'
DEFAULT_PATH_CONFIG = 'conf/ocr_config.ini'


class OCRPipeline():
    """Control pipeline workflow"""

    def __init__(self, scandata_path, conf_file=None, log_dir=None):
        """OCR Pipeline init

        Args:
            scandata_path (str): Represents single dir or comma-separated directories.
            conf_file (str, optional): Path to configuration file.
                                       Defaults to 'conf/ocr_config.ini'.
            log_dir (str, optional): Path to log directory. Defaults to None.

        Raises:
            ValueError: If no proper configuration provided or guessed.
        """
        self.cfg = configparser.ConfigParser()
        _path = scandata_path
        if ',' in _path:
            _path = list(set(_path.split(',')))
        self.data_path = _path
        self.pipeline_file_paths = []
        self.tesseract_args = {}
        if conf_file is None:
            project_dir = os.path.dirname(__file__)
            conf_file = os.path.join(project_dir, DEFAULT_PATH_CONFIG)
        read_files = self.cfg.read(conf_file)
        if not read_files:
            raise ValueError('No Pipeline-Configuration!')

        self._init_logger(log_dir)
        self.prepare_workdir()

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

    def _init_logger(self, log_dir=None):
        if log_dir:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            self.cfg['pipeline']['logdir'] = log_dir
        fallback_logdir = os.path.join(
            tempfile.gettempdir(), 'ocr-pipeline-log')
        logger_folder = self.cfg.get('pipeline', 'logdir')
        today = time.strftime('%Y-%m-%d', time.localtime())
        # path exists but cant be written
        if not os.path.exists(logger_folder) or not os.access(
                logger_folder, os.W_OK):
            logger_folder = fallback_logdir
            # use default project log path
            # create if not existing
            if not os.path.exists(logger_folder):
                os.makedirs(logger_folder)
        # set data_path path as logfile prefix
        if isinstance(self.data_path, str):
            file_prefix = os.path.basename(self.data_path)
            # save check if path got trailing slash
            if self.data_path.endswith("/"):
                file_prefix = 'ocr'
        else:
            file_prefix = 'ocr_pipeline'

        self.logfile_name = os.path.join(
            logger_folder, f"{file_prefix}_{today}.log")
        conf_logname = {'logname': self.logfile_name}

        # config file location
        project_dir = os.path.dirname(__file__)
        conf_file_location = os.path.join(
            project_dir, 'conf', 'ocr_logger_config.ini')
        logging.config.fileConfig(conf_file_location, defaults=conf_logname)
        logger_name = self.cfg.get('pipeline', 'logger_name')
        self.logger = logging.getLogger(logger_name)
        self.logger.info("init pipeline with config '%s' at '%s'",
                         conf_file_location, self.logfile_name)

    def _set_mark(self, mark, path_dir=None, preceeding=None):
        """Mark given directory with pipeline-at-work.

        Args:
            mark (str):
                Label to set.
            path_dir (str, optional):
                Path to place mark.
                Defaults to None.
            preceeding (str, optional):
                Label of preceeding mark within pat_dir.
                Defaults to None.
        """

        # set default mark dir to data_root
        if not path_dir and isinstance(self.data_path, str):
            path_dir = self.data_path
        right_now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

        if not preceeding:
            preceeding = self.cfg.get('pipeline', 'mark_lock',
                                      fallback=DEFAULT_MARK_BUSY)
        old_marker = os.path.join(path_dir, preceeding)
        with open(old_marker, 'a+', encoding="UTF-8") as m_file:
            m_file.write(f"\n{right_now} mark state {mark}")
        os.rename(old_marker, os.path.join(path_dir, mark))

    def mark_fail(self):
        """mark state pipeline failed"""

        file_fail = self.cfg.get('pipeline', 'mark_fail',
                                 fallback=DEFAULT_MARK_FAIL)
        self._set_mark(file_fail)

    def mark_done(self):
        """Mark state pipeline succeded"""

        file_done = self.cfg.get('pipeline', 'mark_done',
                                 fallback=DEFAULT_MARK_DONE)
        self._set_mark(file_done)

    def prepare_workdir(self, workdir=None):
        """prepare workdir: create or clear if necessary"""

        workdir_tmp = workdir
        if not workdir_tmp:
            workdir_tmp = self.cfg.get('pipeline', 'workdir')
            self.logger.warning("no workdir set, use '%s'", workdir_tmp)

        if not os.path.isdir(workdir_tmp):
            if os.access(workdir_tmp, os.W_OK):
                os.makedirs(workdir_tmp)
            else:
                self.logger.warning("workdir '%s' not writable, use tmp dir",
                                    workdir_tmp)
                workdir_tmp = '/tmp/ocr-pipeline-workdir'
                if os.path.exists(workdir_tmp):
                    self._clean_workdir(workdir_tmp)
                os.makedirs(workdir_tmp, exist_ok=True)
        else:
            self._clean_workdir(workdir_tmp)

        return workdir_tmp

    def _clean_workdir(self, the_dir):
        """clear previous work artifacts"""

        self.logger.info("clean existing workdir '%s'", the_dir)
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
        if not isinstance(self.data_path, str):
            self.logger.warning('unable to choose store for estm data: %s',
                                str(self.data_path))
            return

        file_name = os.path.basename(self.data_path)
        file_path = os.path.join(
            self.data_path, f"{file_name}_{end_time}.wtr")
        self.logger.info("store mean '%.3f' in '%s'",
                         aggregations[0], file_path)
        if aggregations:
            (mean, bins) = aggregations
            b_1 = len(bins[0])
            b_2 = len(bins[1])
            b_3 = len(bins[2])
            b_4 = len(bins[3])
            b_5 = len(bins[4])
            n_v = len(valids)
            n_i = len(invalids)
            self.logger.info("WTE (Mean): '%.1f' (1: %d/%d, ... 5: %d/%d)",
                             mean, b_1, n_v, b_5, n_v)
            with open(file_path, 'w', encoding="UTF-8") as outfile:
                outfile.write(
                    f"{mean},{b_1},{b_2},{b_3},{b_4},{b_5},{len(estms)},{n_i}\n")
                for s in sorteds:
                    outfile.write(
                        f"{s[0]},{s[1]:.3f},{s[2]},{s[3]},{s[4]},{s[5]},{s[6]},{s[7]}\n")
                outfile.write("\n")
                return file_path

    def input_sorted(self, recursive=False):
        """Calculate data paths

        Args:
            recursive (bool, optional):
                Whether to collect paths recursive
                from given data_path, worse for complex file trees.
                Defaults to False.

        Returns:
            list(str): List of data paths
        """

        exts = [self.cfg.get('pipeline', 'file_ext', fallback='jpg')]
        if "," in exts[0]:
            exts = exts[0].split(",")

        def _file_ext_matches(path):
            for file_ext in exts:
                if str(path).endswith(file_ext):
                    return True
            return False

        def _marked(path, mark=None):
            """Determine if given mark exists in path

            Args:
                path (str): Path to inspect
                mark (str, optional): Mark to filter.
                    Defaults to None.

            Returns:
                bool: Mark contained or not set?
            """

            if not mark:
                return True
            return mark in os.listdir(path)

        paths = []
        mark_open = self.cfg.get('pipeline', 'mark_open', fallback=None)
        if recursive and isinstance(self.data_path, str):
            self.logger.debug("recursive sub-directories having '%s'",
                              mark_open)
            paths = [os.path.join(curr, f)
                     for curr, _, files in os.walk(self.data_path)
                     for f in files
                     if _file_ext_matches(f)
                     and _marked(curr, mark_open)]
        else:
            if isinstance(self.data_path, list):
                dirs = self.data_path
                self.logger.debug("inspect dirs '%s'", dirs)
                paths = [os.path.join(a_dir, p.name)
                         for a_dir in dirs
                         for p in pathlib.Path(a_dir).iterdir()
                         if _file_ext_matches(p.name)
                         and _marked(a_dir, mark_open)]
            if isinstance(self.data_path, str):
                self.logger.debug("inspect single dir '%s'", self.data_path)
                paths = [os.path.join(self.data_path, p.name)
                         for p in pathlib.Path(self.data_path).iterdir()
                         if _file_ext_matches(p.name)]
        # sort and eliminate duplicate paths
        self.pipeline_file_paths = sorted(list(set(paths)))
        return self.pipeline_file_paths

    def lock_paths(self):
        """Lock *all* current directories for other ocr-workers"""

        open_marker = self.cfg.get('pipeline', 'mark_open')
        lock_marker = self.cfg.get('pipeline', 'mark_lock')
        for file_path in self.pipeline_file_paths:
            dir_name = os.path.dirname(file_path)
            file_names = [f.name for f in os.scandir(dir_name)]
            if lock_marker not in file_names:
                self.logger.debug("lock path '%s' for processing",
                                  dir_name)
                if open_marker in file_names:
                    self._set_mark(lock_marker, dir_name, open_marker)
                else:
                    self._set_mark(lock_marker, dir_name)

    def unlock_paths(self):
        """Un-Lock all before sealed directories"""

        lock_marker = self.cfg.get('pipeline', 'mark_lock')
        done_marker = self.cfg.get('pipeline', 'mark_done')
        for file_path in self.pipeline_file_paths:
            dir_name = os.path.dirname(file_path)
            for dir_entry in os.scandir(dir_name):
                if lock_marker in dir_entry.name:
                    self.logger.debug("un-lock path '%s'",
                                      dir_name)
                    self._set_mark(done_marker, dir_name, lock_marker)


def profile(func):
    """profile execution time of provided function"""

    func_start = time.time()
    func()
    func_end = time.time()
    func_delta = func_end - func_start
    label = str(func).split()[4].split('.')[2]
    return f"{label} run {func_delta:.2f}s"


def _execute_pipeline(*args):
    number = args[0][0]
    start_path = args[0][1]
    batch_label = f"{number:04d}/{len(INPUT_PATHS):04d}"
    next_in = start_path
    file_name = os.path.basename(start_path)
    outcome = (file_name, MARK_MISSING_ESTM)

    try:
        the_steps = pipeline.get_steps()
        pipeline.logger.info("[%s] [%s] start pipeline with %d steps",
                             file_name, batch_label, len(the_steps))

        # for step in STEPS:
        for step in the_steps:
            step.path_in = next_in
            if isinstance(step, StepIOExtern):
                pipeline.logger.debug("[%s] %s", file_name, step.cmd)

            # the actual execution
            profile_result = profile(step.execute)

            # log current step
            if hasattr(step, 'statistics') and len(step.statistics) > 0:
                if profile_result and isinstance(step, StepEstimateOCR):
                    _qa_step: StepEstimateOCR = step
                    if not _qa_step.enabled():
                        pipeline.logger.warning("[%s] %s configured but disabled",
                                                file_name, _qa_step.__class__.__name__)
                    outcome = (file_name,) + _qa_step.statistics
                pipeline.logger.info("[%s] %s, statistics: %s",
                                      file_name, profile_result,
                                      str(step.statistics))
            else:
                pipeline.logger.debug("[%s] %s", file_name, profile_result)

            # prepare next step
            if hasattr(step, 'path_next') and step.path_next is not None:
                pipeline.logger.debug("[%s] step.path_next: %s",
                                      file_name, step.path_next)
                next_in = step.path_next

        pipeline.logger.info("[%s] [%s] done pipeline with %d steps",
                             file_name, batch_label, len(the_steps))
        return outcome

    # if a single step-based images crashes, we will go on anyway
    except StepException as exc:
        pipeline.logger.error(
            "[%s] %s: %s",
            start_path,
            step,
            exc.args[0])
    # OSError means something really severe, like
    # non-existing resources/connections that will harm
    # all images in pipeline, therefore signal halt
    except OSError as os_exc:
        pipeline.logger.critical(
            "[%s] %s: %s",
            start_path,
            step,
            str(os_exc))
        sys.exit(1)


# main entry point
if __name__ == '__main__':
    APP_ARGUMENTS = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter)
    APP_ARGUMENTS.add_argument(
        "data_path",
        help="path to data_path dir")
    APP_ARGUMENTS.add_argument(
        "-r",
        "--recursive",
        required=False,
        default=False,
        action='store_true',
        help="iterate recursive from data_path path top-down")
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

    DATA_PATH = ARGS["data_path"]
    if "," not in DATA_PATH and not os.path.isdir(DATA_PATH):
        print(
            f"[ERROR] data_path path '{DATA_PATH}' invalid!", file=sys.stderr)
        sys.exit(1)
    CONFIG = ARGS.get('config', DEFAULT_PATH_CONFIG)

    # create ocr pipeline wrapper instance
    pipeline = OCRPipeline(DATA_PATH, CONFIG)

    # update pipeline configuration with cli args
    pipeline.merge_args(ARGS)
    EXECUTORS = pipeline.cfg.getint('pipeline', 'executors')
    INPUT_PATHS = pipeline.input_sorted(ARGS['recursive'])
    pipeline.logger.info("%d inputs for pipeline", len(INPUT_PATHS))
    INPUT_NUMBERED = [(i, img)
                      for i, img in enumerate(INPUT_PATHS, start=1)]

    # set start time
    START_TS = time.time()

    try:
        # lock directories for concurrent ocr-workers
        pipeline.lock_paths()

        # perform sequential part of pipeline with parallel processing
        with concurrent.futures.ProcessPoolExecutor(max_workers=EXECUTORS) as executor:
            RESULTS = list(executor.map(_execute_pipeline, INPUT_NUMBERED))
            pipeline.logger.info("having %d workflow results", len(RESULTS))
            estimations = [r for r in RESULTS if r is not None and r[1] > MARK_MISSING_ESTM]
            if estimations:
                pipeline.store_estimations(estimations)
            else:
                pipeline.logger.warning("no ocr qa data available")
    except OSError as exc:
        pipeline.logger.error("%s", str(exc))
        pipeline.mark_fail()
        raise OSError from exc

    if isinstance(pipeline.data_path, str):
        pipeline.mark_done()
    else:
        # un-lock directories with recursive processing
        pipeline.unlock_paths()
    DELTA_TS = (time.time()) - START_TS
    MSG_RT = f'{DELTA_TS:.2f} sec ({math.floor(DELTA_TS/60)}min {math.floor(DELTA_TS % 60)}sec)'
    END_TS = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    pipeline.logger.info("pipeline finished '%s' (%s)", END_TS, MSG_RT)
