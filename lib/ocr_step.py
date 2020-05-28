# -*- coding: utf-8 -*-
"""ULB OCR Pipeline Steps API"""

from abc import ABC, abstractmethod
from collections import OrderedDict
import os
import re
import shutil
import subprocess


class StepException(Exception): pass

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

    def __init__(self, path_in, dict_char):
        super().__init__(path_in)
        self.dict_char = dict_char
        self.lines_new = []
        self.replacements = {}


    def must_backup(self):
        """Determine if Backup file must be written"""

        return True


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

    def __init__(self, path_in, regex_replacements):
        super().__init__(path_in, {})
        self.regex_replacements = regex_replacements
        self.lines_new = []


    def must_backup(self):
        return False


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
        if os.path.exists(self.path_in):
            if os.path.basename(self.path_in).endswith(self.suffix):
                os.remove(self.path_in)
                self.file_removed = True

    def is_removed(self):
        """Was File Removed?"""

        return self.file_removed
