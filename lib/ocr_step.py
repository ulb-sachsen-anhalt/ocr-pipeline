# -*- coding: utf-8 -*-
"""ULB OCR Pipeline Steps API"""

import os
import re
import shutil
import subprocess
import sys

from abc import (
    ABC, abstractmethod
)
from collections import (
    OrderedDict
)
from typing import (
    Dict
)

import lxml.etree as ET

# 3rd party import
import requests


NAMESPACES = {'alto': 'http://www.loc.gov/standards/alto/ns-v3#'}

# defaults language tool
DEFAULT_LANGTOOL_URL = 'http://localhost:8010'
DEFAULT_LANGTOOL_LANG = 'de-DE'
DEFAULT_LANGTOOL_RULE = 'GERMAN_SPELLER_RULE'


def split_path(path_in):
    """create tuple with dirname and filename (minus ext)"""
    path_in_folder = os.path.dirname(path_in)
    file_name_in = path_in.split(os.sep)[-1]
    filename = file_name_in.split('.')[0]
    return (path_in_folder, filename)


def dict2line(the_dict, the_glue):
    """create string from dictionary"""
    def impl(key, val, glue):
        if val:
            return ' ' + key + glue + str(val)
        return ' ' + key
    return ''.join([impl(k, v, the_glue) for k, v in the_dict.items()]).strip()


class StepException(Exception):
    """Mark Step Execution Exception"""


class StepI(ABC):
    """step that handles input data"""

    @abstractmethod
    def execute(self):
        """Step Action to execute"""

    @property
    def path_in(self):
        """Input data path"""
        return self._path_in

    @path_in.setter
    def path_in(self, path_in):
        if not os.path.exists(path_in):
            raise RuntimeError('path {} invalid'.format(path_in))
        if not isinstance(path_in, str):
            path_in = str(path_in)
        self._path_in = path_in
        (self._path_in_dir, self._filename) = split_path(self._path_in)


class StepIO(StepI):
    """Extension that reads and writes Data for next step"""

    def __init__(self):
        super().__init__()
        self._filename = None
        self._path_in_dir = None
        self._path_next = None
        self._path_next_dir = None

    @property
    def path_next(self):
        """calculate path_out for result data"""
        return self._path_next

    @path_next.setter
    def path_next(self, path_next):
        self._path_next = path_next


class StepIOExtern(StepIO):
    """Call external Tool with additional params"""

    def __init__(self, params):
        super().__init__()
        self._cmd = None
        self._bin = None
        try:
            self._params = OrderedDict(params)
            if 'type' in self._params:
                del self._params['type']
        except ValueError as exc:
            msg = f'Invalid Dictionary for arguments provided: "{exc.args[0]}" !'
            raise StepException(msg) from exc

    def execute(self):
        subprocess.run(self.cmd, shell=True, check=True)

    @property
    def cmd(self):
        """return cmdline for execution"""
        return self._cmd

    @cmd.setter
    def cmd(self, cmd):
        self._cmd = cmd


class StepTesseract(StepIOExtern):
    """Central Call to Tessract OCR"""

    def __init__(self, params: Dict):
        super().__init__(params)
        self._bin = 'tesseract'
        if 'tesseract_bin' in self._params:
            self._bin = self._params['tesseract_bin']
            del self._params['tesseract_bin']
        if 'path_out_dir' in self._params:
            self._path_out_dir = self._params['path_out_dir']

        # common process params
        # where to store alto data, dpi and language
        xtras = self._params.get('extra')
        if xtras:
            del self._params['extra']
            self._params.update({xtras: None})
        models = None
        if 'model_configs' in self._params:
            models = self._params.get('model_configs')
            del self._params['model_configs']
        if '-l' in self._params:
            models = self._params.get('-l')
            del self._params['-l']
        if models is not None:
            self._params.update({'-l': models})
        # regular configured output
        output_configs = self._params.get('output_configs', 'alto').split()
        if 'output_configs' in self._params:
            del self._params['output_configs']
        # otherwise output
        outputs = [k for k, v in self._params.items() if v is None and k in [
            'alto', 'txt', 'pdf']]
        if len(outputs) > 0:
            for output in outputs:
                del self._params[output]
        final = ' '.join(sorted(set(output_configs + outputs)))
        self._params.update({final: None})
        self._params.move_to_end(final)

    @property
    def path_next(self):
        _filename = self._filename
        if not _filename.endswith('.xml'):
            _filename += '.xml'

        # calculate abs path
        self._path_next = None
        if self._path_next_dir:
            self._path_next = os.path.join(self._path_next_dir, _filename)
        else:
            self._path_next = os.path.join(self._path_in_dir, _filename)
        return self._path_next

    @property
    def cmd(self):
        """
        Update Command with specific in/output paths
        """
        out_file = os.path.splitext(self.path_next)[0]
        self._cmd = f"{self._bin} {self.path_in} {out_file} {dict2line(self._params, ' ')}"
        return self._cmd


def parse_dict(the_dict):
    """parse dictionary from string without worrying about proper json syntax"""
    if isinstance(the_dict, str):
        the_dict = the_dict.replace('{', '').replace('}', '')
        tkns = the_dict.split(',')
        if len(tkns) > 1:
            return {tkn.split(':')[0].strip(): tkn.split(':')[
                1].strip() for tkn in tkns}
    if isinstance(the_dict, dict):
        return the_dict
    return {}


class StepPostReplaceChars(StepIO):
    """Postprocess: Replace suspicious character sequences"""

    def __init__(self, params: Dict):
        super().__init__()
        dict_chars = params.get('dict_chars', '{}')
        self.dict_chars = parse_dict(dict_chars)
        self.lines_new = []
        self._replacements = {}
        self._must_backup = params.get('must_backup', False)

    def must_backup(self):
        """Determine if Backup file must be written"""
        return str(self._must_backup).upper() == 'TRUE'

    def execute(self):
        file_handle = open(self.path_in, 'r')
        lines = file_handle.readlines()
        file_handle.close()
        self._replace(lines)

        # if replacements are done, backup original file
        if self._replacements and self.must_backup():
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
            for (k, val) in self.dict_chars.items():
                if k in line:
                    line = line.replace(k, val)
                    self._update_replacements(k)
            self.lines_new.append(line)

    def _set_path_out(self):
        return self.path_in

    def _update_replacements(self, key):
        n_repl = 1

        if self._replacements.get(key):
            n_repl = self._replacements.get(key) + 1

        self._replacements.update({key: n_repl})

    @property
    def statistics(self):
        """Statistics about Replacements"""
        if self._replacements:
            return [':'.join([k, str(v)])
                    for k, v in self._replacements.items()]
        return []


class StepPostReplaceCharsRegex(StepPostReplaceChars):
    """Postprocess: Replace via regular expressions"""

    def __init__(self, params: Dict):
        super().__init__({})
        self.pattern = params['pattern']
        self.old = params['old']
        self.new = params['new']
        self.lines_new = []

    def _replace(self, lines):
        for line in lines:
            # for string_element in self.regex_replacements:
            matcher = re.search(self.pattern, line)
            if matcher:
                match = matcher.group(1)
                replacement = match.replace(self.old, self.new)
                line = line.replace(match, replacement)
                self._update_replacements(match + '=>' + replacement)
            self.lines_new.append(line)


class StepPostMoveAlto(StepIO):
    """Postprocess: move Alto file to original scandata folder"""

    def __init__(self, params: Dict):
        super().__init__()
        if 'path_target' in params:
            self._path_out = params['path_target']

    def execute(self):
        shutil.copyfile(self._path_in, self._path_out)

    @property
    def path_next(self):
        (folder, _) = split_path(self._path_out)
        return os.path.join(folder, self._filename + '.xml')

    @path_next.setter
    def path_next(self, path_target):
        (folder, _) = split_path(path_target)
        self._path_out = os.path.join(folder, self._filename + '.xml')


class StepPostRemoveFile(StepI):
    """Cleanup and remove temporal TIF-Files before they flood the Discs"""

    def __init__(self, params: Dict):
        super().__init__()
        self._file_removed = False
        self._suffix = params.get('file_suffix', 'tif')

    def execute(self):
        if os.path.exists(self.path_in) and os.path.basename(
                self.path_in).endswith(self._suffix):
            os.remove(self.path_in)
            self._file_removed = True

    def is_removed(self):
        """Was File Removed?"""

        return self._file_removed


class StepEstimateOCR(StepI):
    """Estimate OCR-Quality of current run by using Web-Service language-tool"""

    def __init__(self, params: Dict):
        super().__init__()
        self.service_url = params.get('service_url', DEFAULT_LANGTOOL_URL)
        self.lang = params.get('language', DEFAULT_LANGTOOL_LANG)
        self.rules = params.get('enabled_rules', DEFAULT_LANGTOOL_RULE)
        self.lines = []
        self.hit_ratio = -1.0
        self.n_words = 0
        self.n_errs = 0
        self.n_lines_in = 0
        self.n_wraps = 0
        self.n_shorts = 0
        self.n_lines_out = 0

    def is_available(self):
        """Connection established ?"""

        try:
            requests.head(self.service_url)
        except requests.ConnectionError:
            return False
        return True

    def execute(self):
        self.lines = altolines2textlines(self.path_in)
        if len(self.lines) > 0:
            (word_string, n_lines, n_normed, n_sparse,
             n_dense) = textlines2data(self.lines)
            if word_string:
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
                    raise StepException(f"Invalid connection: {exc}") from exc
                except Exception:
                    raise StepException(f"Invalid data: {sys.exc_info()[0]}")

    def request_data(self, params):
        """Get word errors for text from webservice"""

        response = requests.post(self.service_url, params)
        if not response.ok:
            raise StepException(
                f"'{self.service_url}' returned invalid '{response}!'")
        return response.json()

    def postprocess_response(self, response_data):
        """Collect error information"""

        if 'matches' in response_data:
            total_matches = response_data['matches']

        typo_errors = len(total_matches)
        if typo_errors > self.n_words:
            typo_errors = self.n_words

        self.n_errs = typo_errors
        if self.n_words <= typo_errors:
            ratio = 0
        else:
            ratio = (self.n_words - typo_errors) / self.n_words * 100
        self.hit_ratio = round(ratio, 3)

    @property
    def statistics(self):
        """Retrive Estimation Details"""

        return (self.hit_ratio,
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


def altolines2textlines(file_path):
    """Convert ALTO Textlines to plain text lines"""

    textnodes = ET.parse(file_path).findall('.//alto:TextLine', NAMESPACES)
    lines = []
    for textnode in textnodes:
        all_strings = textnode.findall('.//alto:String', NAMESPACES)
        words = [s.attrib['CONTENT']
                 for s in all_strings if s.attrib['CONTENT'].strip()]
        if words:
            lines.append(' '.join(words))
    return lines


def textlines2data(lines, minlen=2):
    """Transform text lines after preprocessing into data set"""

    non_empty_lines = [l for l in lines if l.strip()]

    (normalized_lines, n_normalized) = _sanitize_wraps(non_empty_lines)
    filtered_lines = _sanitize_chars(normalized_lines)
    n_sparselines = 0
    dense_lines = []
    for filtered_line in filtered_lines:
        # we do not want lines shorter than 2 chars
        if len(filtered_line) > minlen:
            dense_lines.append(filtered_line)
        else:
            n_sparselines += 1

    file_string = ' '.join(dense_lines)
    return (file_string, len(lines), n_normalized,
            n_sparselines, len(dense_lines))


def _sanitize_wraps(lines):
    """Sanitize word wraps if last word token ends with '-' and another line following"""

    normalized = []
    n_normalized = 0
    for i, line in enumerate(lines):
        if i < len(lines) - 1 and line.endswith("-"):
            next_line_tokens = lines[i + 1].split()
            nextline_first_token = next_line_tokens.pop(0)
            lines[i + 1] = ' '.join(next_line_tokens)
            line = line[:-1] + nextline_first_token
            n_normalized += 1
        normalized.append(line)
    return (normalized, n_normalized)


def _sanitize_chars(lines):
    """Replace or remove nonrelevant chars for current german word error rate"""

    sanitized = []
    for line in lines:
        text = line.strip()
        bad_chars = '0123456789“„"\'?!*.;:-=[]()|'
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


class StepPostprocessALTO(StepIO):
    """Postprocess ALTO XML
    optional params
    * 'page_prefix' : prefix which will be preponed to the Page@ID-attribute
      if not set, use 'p'
    """

    def __init__(self, params=None):
        super().__init__()
        self.params = params

    def execute(self):
        """All enrichment assumes there's only a single Page present
        within the whole ALTO file, thus any text content or
        attribute values *always* target the very first
        * sourceImageInformation/fileName
        * Layout/Page
        """

        xml_root = ET.parse(self.path_in)
        the_ns = re.match(r'^\{(.*)\}\w+', xml_root.getroot().tag)[1]

        # enrich sourceImageInformation/fileIdentifier
        file_name = os.path.basename(self.path_in)
        file_id = file_name.split('.')[0]
        alto_descr = xml_root.findall('.//alto:Description', NAMESPACES)[0]
        source_infos = alto_descr.findall('.//alto:sourceImageInformation', NAMESPACES)
        if source_infos:
            StepPostprocessALTO._append_source_infos(source_infos[0], file_name, the_ns)
        else:
            source_info = ET.SubElement(alto_descr,
                f'{{{the_ns}}}sourceImageInformation')
            StepPostprocessALTO._append_source_infos(source_info, file_name, the_ns)
        # enrich Page@ID for only *first* page
        first_page = xml_root.findall('.//alto:Layout/alto:Page', NAMESPACES)[0]
        prefix = self.params['page_prefix'] if self.params and 'page_prefix' in self.params else 'p'
        expected_id = f'{prefix}{file_id}'
        if first_page.attrib['ID'] != expected_id:
            first_page.attrib['ID'] = expected_id

        # remove empty sections
        drop_empty_contents(xml_root)

        write_xml_file(xml_root, self.path_in)

    @staticmethod
    def _append_source_infos(descr_tree, file_name, namespace):
        # fileIdentifier required
        file_id = file_name.split('.')[0]
        alto_file_id = descr_tree.find('alto:fileIdentifier', NAMESPACES)
        if not alto_file_id:
            ET.SubElement(descr_tree,
                f'{{{namespace}}}fileIdentifier').text = file_id
        else:
            alto_file_id.text = file_id
        # enrich file_name, too
        _file_names = descr_tree.findall('alto:fileName', NAMESPACES)
        if not _file_names:
            ET.SubElement(descr_tree,
                f'{{{namespace}}}fileName').text = file_name
        else:
            _file_names[0].text = file_name


def drop_empty_contents(xml_root):
    """
    clear empty content sections
    walk up and clear afterward empty parent structures too"""

    all_empty_strings = [e
                         for e in xml_root.findall('.//alto:String', NAMESPACES)
                         if e.attrib['CONTENT'].strip() == '']
    for empty in all_empty_strings:
        parent_line = empty.getparent()
        parent_line.remove(empty)
        # if now no String data available (but maybe SP), drop 'em all
        if not parent_line.findall('alto:String', NAMESPACES):
            parent_block = parent_line.getparent()
            parent_block.remove(parent_line)
            if not parent_block.getchildren():
                parent_super = parent_block.getparent()
                parent_super.remove(parent_block)
                tag_name = parent_super.tag
                if not parent_super.getchildren() and tag_name.endswith('Block'):
                    printspace = parent_super.getparent()
                    printspace.remove(parent_super)


def write_xml_file(xml_root, outfile):
    """ write xml pretty printed to outfile """

    xml_string = ET.tostring(xml_root, pretty_print=True, encoding='UTF-8')
    pretty_parser = ET.XMLParser(
        resolve_entities=False, strip_cdata=False, remove_blank_text=True)
    xml_root_new = ET.fromstring(xml_string, pretty_parser)
    xml_formatted = ET.tostring(xml_root_new,
                                pretty_print=True,
                                encoding='UTF-8').decode('UTF-8')
    formatted_file_content = '{}'.format(xml_formatted)
    formatted_file_content = formatted_file_content.encode(
        'UTF-8').replace(b'\n', b'\r\n')
    with open(outfile, 'wb') as file_handler:
        file_handler.write(formatted_file_content)
