"""OCR Data Model"""

import abc
import sys
from functools import reduce

import numpy as np

# namespaces of different OCR-Formats
XML_NS = {
    'alto3': 'http://www.loc.gov/standards/alto/ns-v3#',
    'alto4': 'http://www.loc.gov/standards/alto/ns-v4#',
    'page2013': 'http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15',
    'page2019': 'http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15'}

# clear unwanted marks for single wordlike tokens
CLEAR_MARKS = [
    u'\u200f',  # 'RIGHT-TO-LEFT-MARK'
    u'\u200e',  # 'LEFT-TO-RIGHT-MARK'
    u'\ufeff',  # 'ZERO WIDTH NO-BREAK SPACE', the char formerly known as 'BOM'
    u'\u200c',  # 'ZERO WIDTH NON-JOINER
    u'\u202c'   # 'POP DIRECTIONAL FORMATTING
]


class TextLine(abc.ABC):
    """
    TextLine from structured OCR-Data
    """

    def __init__(self, element, namespace):
        self.element = element
        self.namespace = namespace
        self.element_id = None
        self.valid = True
        self.text_words = []
        self.reorder = None
        self.vertical = False

    @abc.abstractmethod
    def set_id(self):
        """Determine identifier"""

    @abc.abstractmethod
    def set_text(self):
        """Determine list of word tokens"""

    def get_shape(self, _):
        """
        Return TextLine shape
        Optional(PAGE): Box filled with median color value
        or the_gray tone to fit rectangular shape
        """

    def get_textline_content(self) -> str:
        """
        Set TextLine contents from it's included word tokens
        reorder order of tokens if required
        """

        aggregat = ' '.join(self.text_words)
        if self.reorder:
            return reduce(lambda c, p: p + ' ' + c, self.text_words)
        return aggregat

    def __repr__(self):
        the_clazz = self.__class__.__name__
        return '{}[{}]:{}'.format(the_clazz, self.element_id, self.get_textline_content())


class ALTOLine(TextLine):
    """Extract TextLine Information from ALTO Data"""

    def __init__(self, element, namespace):
        super().__init__(element, namespace)
        self.set_id()
        self.set_text()
        if self.valid:
            self.shape = self.get_shape(self.element)

    def set_id(self):
        self.element_id = self.element.attrib['ID']

    def set_text(self):
        strings = self.element.findall(f'{self.namespace}:String', XML_NS)
        self.text_words = [e.attrib['CONTENT'] for e in strings]

    def get_shape(self, element):
        x_1 = int(element.attrib['HPOS'])
        y_1 = int(element.attrib['VPOS'])
        y_2 = y_1 + int(element.attrib['HEIGHT'])
        x_2 = x_1 + int(element.attrib['WIDTH'])
        return [(x_1, y_1), (x_2, y_1), (x_2, y_2), (x_1, y_2)]


class PageLine(TextLine):
    """Extract TextLine Information from PAGE Data"""

    def __init__(self, element, namespace, reorder):
        super().__init__(element, namespace)
        self.set_id()
        self.set_text()
        if self.valid:
            self.reorder = reorder
            self.shape = self.get_shape(self.element)

    def set_id(self):
        self.element_id = self.element.attrib['id']

    def set_text(self):
        """
        * set words as preferred text source, otherwise use text line
        * drop rtl-mark if contained
        * print lines without coords
        """

        texts = []
        text_els = self.element.findall(f'{self.namespace}:Word', XML_NS)
        for text_el in text_els:
            top_left = to_center_coords(text_el, self.namespace, self.vertical)
            if not top_left:
                elem_id = text_el.attrib['id']
                msg = f"Invalid Coords of Word '{elem_id}' in '{self.element_id}'!"
                raise RuntimeError(msg)
            texts.append(text_el)

        # if no Word assume at least TextLine exists
        if not text_els:
            top_left = to_center_coords(self.element, self.namespace, self.vertical)
            if not top_left:
                elem_id = self.element.attrib['id']
                print("[ERROR  ] skip '{}': invalid coords!".format(
                    elem_id), file=sys.stderr)
                self.valid = False
                return
            texts.append(self.element)

        sorted_els = sorted(
            texts,
            key=lambda w: int(to_center_coords(w, self.namespace, self.vertical)))
        unicodes = [
            w.find(
                f'.//{self.namespace}:Unicode',
                XML_NS) for w in sorted_els]
        self.text_words = [u.text.strip() for u in unicodes if u.text]

        # elimiate read order mark
        for i, strip in enumerate(self.text_words):
            strip = self.text_words[i]
            for mark in CLEAR_MARKS:
                if mark in strip:
                    self.text_words[i] = strip.replace(mark, '')


    def get_shape(self, element):
        """
        Coordinate data from current OCR-D-Workflows can contain
        lots of points, therefore additional calculations are required
        """

        p_attr = element.find(
            f'{self.namespace}:Coords',
            XML_NS).attrib['points']
        numbers = [int(n) for pair in p_attr.split() for n in pair.split(',')]

        # group clustering idiom
        points = list(zip(*[iter(numbers)] * 2))

        return np.array((points), dtype=np.uint32)


def _determine_namespace(xml_data):
    root_tag = xml_data.xpath('namespace-uri(.)')
    return [k for (k, v) in XML_NS.items() if v == root_tag][0]


def coords_center(coord_tokens):
    """Get Point-Pairs from textual represented coordinates"""
    vals = [int(b)
            for a in map(lambda e: e.split(','), coord_tokens)
            for b in a]
    point_pairs = list(zip(*[iter(vals)]*2))
    return tuple(map(lambda c: sum(c) / len(c), zip(*point_pairs)))


def to_center_coords(elem, namespace:str, vertical:bool=False):
    """Calculate center coords
    """
    coords = elem.find(f'{namespace}:Coords', XML_NS)
    coord_tokens = coords.attrib['points'].split()
    if len(coord_tokens) > 0:
        center = coords_center(coord_tokens)
        if vertical:
            return center[1]
        return center[0]
    return None


def get_lines(xml_data, min_len=2, reorder=False):
    """Create text_lines from OCR-Data"""

    _text_lines = []
    ns_prefix = _determine_namespace(xml_data)
    if 'alto' in ns_prefix:
        _text_lines = get_alto_lines(xml_data, ns_prefix, min_len)
    elif ns_prefix in ('page2013', 'page2019'):
        _text_lines = get_page_lines(xml_data, ns_prefix, min_len, reorder)

    # proceed only valid lines
    return [t for t in _text_lines if t.valid]


def get_alto_lines(xml_data, ns_prefix:str, min_len:int):
    """Extract lines from ALTO-formats
    """
    all_lines = xml_data.findall(f'.//{ns_prefix}:TextLine', XML_NS)
    all_lines_len = [l for l in all_lines if len(' '.join(
        [s.attrib['CONTENT'] for s in l.findall(f'{ns_prefix}:String', XML_NS)])) >= min_len]
    return [ALTOLine(line, ns_prefix) for line in all_lines_len]


def get_page_lines(xml_data, ns_prefix:str, min_len:int, reorder:bool):
    """Extract lines from PAGE formats
    """
    all_lines = xml_data.findall(f'.//{ns_prefix}:TextLine', XML_NS)
    matchings = []
    for textline in all_lines:
        text_equiv = textline.find(
            f'{ns_prefix}:TextEquiv/{ns_prefix}:Unicode', XML_NS)
        if text_equiv.text:
            stripped = text_equiv.text.strip()
            if len(stripped) and len(stripped) >= min_len:
                matchings.append(textline)
        else:
            words = textline.findall(
                f'{ns_prefix}:Word/{ns_prefix}:TextEquiv/{ns_prefix}:Unicode', XML_NS)
            if len(words):
                base_path = xml_data.getroot().base if xml_data.getroot() is not None else 'n.a.'
                msg = f"{base_path}: just words for line '{textline.attrib['id']}'"
                raise RuntimeError(msg)
    return [PageLine(line, ns_prefix, reorder) for line in matchings]
