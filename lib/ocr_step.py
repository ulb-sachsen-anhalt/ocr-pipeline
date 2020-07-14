# -*- coding: utf-8 -*-
"""ULB OCR Pipeline Steps API"""

from abc import ABC, abstractmethod
from collections import OrderedDict
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

# 3rd party import
import requests



NAMESPACES = {'alto': 'http://www.loc.gov/standards/alto/ns-v3#'}



class StepException(Exception):
    """Mark Step Execution Exception"""



class Step(ABC):
    """Basic abstract Stept Interface"""

    @abstractmethod
    def execute(self):
        """Step Action to execute"""


    def get_name(self):
        """Human-readable Name of step"""

        return self.__class__.__name__


class StepI(Step):
    """Abstract Extension that reads Date for Analyzis"""

    def __init__(self, path_in):
        if not os.path.exists(path_in):
            raise RuntimeError('path {} invalid'.format(path_in))
        self.path_in = path_in


    @abstractmethod
    def execute(self):
        pass


class StepIO(StepI):
    """Abstract Extension that both reads and writes Data"""

    def __init__(self, path_in):
        super().__init__(path_in)
        (self.path_in_folder, self.filename) = StepIO._split_path(self.path_in)
        self.path_out_folder = None
        self.path_out = self._set_path_out()


    @staticmethod
    def _split_path(path_in):
        path_in_folder = os.path.dirname(path_in)
        file_name_in = path_in.split(os.sep)[-1]
        filename = file_name_in.split('.')[0]
        return (path_in_folder, filename)


    @abstractmethod
    def execute(self):
        pass


    @abstractmethod
    def _set_path_out(self):
        """calculate path_out for result data"""



class StepIOExtern(StepIO):
    """Specific Extension of StepIO that calls an external Tool to read and write Data"""

    def __init__(self, path_in, args):
        super().__init__(path_in)
        if not args:
            raise StepException(f'Invalid Dictionary for arguments provided: "{args}" !')
        self.args = args
        self.cmd = self._create_cmd()


    @staticmethod
    def _impl(key, val, glue):
        if val:
            return ' ' + key + glue + str(val)
        return ' ' + key


    def _create_cmd(self):
        return ''.join([StepIOExtern._impl(k, v, self._get_glue()) for k, v in self.args.items()])


    def execute(self):
        subprocess.run(self.cmd, shell=True, check=True)


    @abstractmethod
    def _set_path_out(self):
        pass


    @abstractmethod
    def _get_glue(self):
        pass


    def get_call(self):
        """return created cmdline"""
        return self.cmd



class StepTesseract(StepIOExtern):
    """Central Call to Tessract OCR"""

    def __init__(self, path_in, args, path_out_folder=None):
        super().__init__(path_in, args)
        self.args = OrderedDict(args)
        self.path_out_folder = path_out_folder
        self.path_out = self._set_path_out()
        self.cmd = 'tesseract' + self._create_cmd()


    def update_cmd(self):
        """
        Update Command depending on late knowledge where to store the alto data
        Re-Uses Informations about dpi and language, if provided, create others
        """

        if self.path_out_folder:
            tmp_name = os.path.join(self.path_out_folder, self.filename)
        else:
            tmp_name = os.path.join(self.path_in_folder, self.filename)
        self.args.update({tmp_name: None})
        self.args.move_to_end(tmp_name, last=False)
        self.args.update({self.path_in: None})
        self.args.move_to_end(self.path_in, last=False)
        self.cmd = 'tesseract' + self._create_cmd()


    def _set_path_out(self):
        if self.path_out_folder:
            return os.path.join(self.path_out_folder, self.filename+'.xml')
        return os.path.join(self.path_in_folder, self.filename+'.xml')


    def _get_glue(self):
        return ' '



class StepPostReplaceChars(StepIO):
    """Postprocess: Replace suspicious character sequences"""

    def __init__(self, path_in, dict_char, must_backup=False):
        super().__init__(path_in)
        self.dict_char = dict_char
        self.lines_new = []
        self.replacements = {}
        self.backup = must_backup


    def must_backup(self):
        """Determine if Backup file must be written"""

        return str(self.backup).upper() == 'TRUE'


    def execute(self):
        file_handle = open(self.path_in, 'r')
        lines = file_handle.readlines()
        file_handle.close()

        self._replace(lines)

        # if replacements are done, backup original file
        if self.replacements and self.must_backup():
            self._backup()
        fhandle = open(self.path_in, 'w')
        _ = [fhandle.write(line) for line in self.lines_new]
        fhandle.close()


    def _backup(self):
        dir_name = os.path.dirname(self.path_in)
        label = os.path.splitext(os.path.basename(self.path_in))[0]
        clazz = type(self).__name__
        out_path = os.path.join(dir_name, label + '_before_' + clazz + '.xml')
        shutil.copyfile(self.path_in, out_path)


    def _replace(self, lines):
        for line in lines:
            for (k, val) in self.dict_char.items():
                if k in line:
                    line = line.replace(k, val)
                    self._update_replacements(k)
            self.lines_new.append(line)


    def _set_path_out(self):
        return self.path_in


    def _update_replacements(self, key):
        n_repl = 1

        if self.replacements.get(key):
            n_repl = self.replacements.get(key) + 1

        self.replacements.update({key : n_repl})


    def get_statistics(self):
        """Statistics about Replacements"""
        if self.replacements:
            return [':'.join([k, str(v)]) for k, v in self.replacements.items()]
        return None



class RegexReplacement:
    """Wrap Replacement Expression"""

    def __init__(self, pattern, search, replacer):
        self.pattern = pattern
        self.search = search
        self.replacer = replacer
        self.store_backup = False



class StepPostReplaceCharsRegex(StepPostReplaceChars):
    """Postprocess: Replace via regular expressions"""

    def __init__(self, path_in, regex_replacements, must_backup=None):
        super().__init__(path_in, {}, must_backup=must_backup)
        self.regex_replacements = regex_replacements
        self.lines_new = []


    def _replace(self, lines):
        for line in lines:
            for string_element in self.regex_replacements:
                matcher = re.search(string_element.pattern, line)
                if matcher:
                    match = matcher.group(1)
                    replacement = match.replace(string_element.search, string_element.replacer)
                    line = line.replace(match, replacement)
                    self._update_replacements(match + '=>' + replacement)
            self.lines_new.append(line)



class StepPostMoveAlto(StepIO):
    """Postprocess: move Alto file to original scandata folder"""

    def __init__(self, path_in, path_target):
        self.path_target = path_target
        super().__init__(path_in)


    def execute(self):
        shutil.copyfile(self.path_in, self.path_out)


    def _set_path_out(self):
        (folder, _) = StepIO._split_path(self.path_target)
        return os.path.join(folder, self.filename + '.xml')



class StepPostRemoveFile(StepI):
    """Cleanup and remove temporal TIF-Files before they flood the Discs"""

    def __init__(self, path_in, file_suffix):
        super().__init__(path_in)
        self.file_removed = False
        self.suffix = file_suffix


    def execute(self):
        if os.path.exists(self.path_in) and os.path.basename(self.path_in).endswith(self.suffix):
            os.remove(self.path_in)
            self.file_removed = True

    def is_removed(self):
        """Was File Removed?"""

        return self.file_removed



class StepEstimateOCR(StepI):
    """Estimate OCR-Quality of current run by using Web-Service language-tool"""

    def __init__(self, path_in, service_url, lang=None, rules=None):
        super().__init__(path_in)
        self.lines = []
        self.path_in = path_in
        self.service_url = service_url
        self.file_name = os.path.basename(path_in)
        self.wtr = -1.0
        self.n_words = 0
        self.n_errs = 0
        self.n_lines_in = 0
        self.n_wraps = 0
        self.n_shorts = 0
        self.n_lines_out = 0
        self.lang = lang
        if not lang:
            self.lang = 'de-DE'
        self.rules = rules
        if not self.rules:
            self.rules = 'GERMAN_SPELLER_RULE'


    def is_available(self):
        """Connection established ?"""

        try:
            requests.head(self.service_url)
        except requests.ConnectionError:
            return False
        return True


    def execute(self):
        self.lines = StepEstimateOCR._to_textlines(self.path_in)
        if not self.lines:
            raise StepException(f"No Textlines in '{self.path_in}'!")

        (word_string, n_lines, n_normed, n_sparse, n_dense) = StepEstimateOCR._get_data(self.lines)
        self.n_lines_in = n_lines
        self.n_shorts = n_sparse
        self.n_wraps = n_normed
        self.n_lines_out = n_dense
        self.n_words = len(word_string.split())

        params = {'language': self.lang,
                  'text': word_string,
                  'enabledRules': self.rules,
                  'enabledOnly': 'true'}
        try:
            response_data = self.request_data(params)
            self.postprocess_response(response_data)
        except ConnectionError as exc:
            raise StepException(f"Invalid connection: {exc}")
        except Exception:
            raise StepException(f"Invalid data: {sys.exc_info()[0]}")


    def request_data(self, params):
        """Get word errors for text from webservice"""

        response = requests.post(self.service_url, params)
        if not response.ok:
            raise StepException(f"'{self.service_url}' returned invalid '{response}!'")
        return response.json()


    def postprocess_response(self, response_data):
        """Collect error information"""

        if 'matches' in response_data:
            total_matches = response_data['matches']

        typo_errors = len(total_matches)
        if typo_errors > self.n_words:
            typo_errors = self.n_words

        coef = typo_errors / self.n_words * 100
        self.n_errs = typo_errors
        self.wtr = round(coef, 3)


    @staticmethod
    def _to_textlines(file_path):
        """Convert ALTO Textlines to plain text lines"""

        textnodes = ET.parse(file_path).findall('.//alto:TextLine', NAMESPACES)
        lines = []
        for textnode in textnodes:
            all_strings = textnode.findall('.//alto:String', NAMESPACES)
            words = [s.attrib['CONTENT'] for s in all_strings if s.attrib['CONTENT'].strip()]
            if words:
                lines.append(' '.join(words))
        return lines


    @staticmethod
    def _get_data(lines):
        """Transform text lines after preprocessing into data set"""

        non_empty_lines = [l for l in lines if l.strip()]

        (normalized_lines, n_normalized) = StepEstimateOCR._sanitize_wraps(non_empty_lines)
        filtered_lines = StepEstimateOCR._sanitize_chars(normalized_lines)
        n_sparselines = 0
        dense_lines = []
        for filtered_line in filtered_lines:
            # we do not want lines shorter than 2 chars
            if len(filtered_line) > 2:
                dense_lines.append(filtered_line)
            else:
                n_sparselines += 1

        file_string = ' '.join(dense_lines)
        return (file_string, len(lines), n_normalized, n_sparselines, len(dense_lines))


    @staticmethod
    def _sanitize_wraps(lines):
        """Sanitize word wraps if last word token ends with '-' and another line following"""

        normalized = []
        n_normalized = 0
        for i, line in enumerate(lines):
            if i < len(lines)-1 and line.endswith("-"):
                next_line_tokens = lines[i+1].split()
                nextline_first_token = next_line_tokens.pop(0)
                lines[i+1] = ' '.join(next_line_tokens)
                line = line[:-1] + nextline_first_token
                n_normalized += 1
            normalized.append(line)
        return (normalized, n_normalized)


    @staticmethod
    def _sanitize_chars(lines):
        """Replace or remove nonrelevant chars for current german word error rate"""

        sanitized = []
        for line in lines:
            text = line.strip()
            bad_chars = '0123456789“„"\'?!*:-=[]()'
            text = ''.join([c for c in text if not c in bad_chars])
            if '..' in text:
                text = text.replace('..', '')
            if '  ' in text:
                text = text.replace('  ', ' ')
            if 'ſ' in text:
                text = text.replace('ſ', 's')
            text = ' '.join([t for t in text.split() if len(t) > 1])
            sanitized.append(text)

        return sanitized


    def get(self):
        """Retrive Estimation Details"""

        return (self.wtr,
                self.n_words,
                self.n_errs,
                self.n_lines_in,
                self.n_wraps,
                self.n_shorts,
                self.n_lines_out)


    @staticmethod
    def analyze(results, bins=5, step_bin=15):
        """Get insights and aggregate results in n bins"""

        if results:
            n_results = len(results)
            mean = round(sum([e[1] for e in results]) / n_results, 3)

            bin_counts = []
            i = 0
            while i < bins:
                bin_counts.append([])
                i += 1

            for result in results:
                target_bin = round(result[1] // step_bin)
                if not target_bin < bins:
                    target_bin = bins - 1
                bin_counts[target_bin].append(result)

            return (mean, bin_counts)
