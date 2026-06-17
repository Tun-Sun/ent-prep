"""MathML → LaTeX converter for the test-ent.kz parser.

Self-contained (no Django, no third-party deps) so it can be unit-tested in
isolation and reused by other commands.

Handles the subset emitted by test-ent.kz pages:
    math, mrow, mi, mn, mo, mtext, mspace, mfrac, msqrt, mroot,
    msub, msup, msubsup, mover, munder, mfenced, mstyle, merror, mpadded

Output is LaTeX wrapped in ``\\( ... \\)`` for inline rendering via KaTeX
(matching the FormattedText component's expected delimiters).
"""
import re

__all__ = ['mathml_to_latex', 'convert_single_math']


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(
    r'(?P<open><(?P<oname>[a-zA-Z]+)(?:\s[^>]*)?>)'
    r'|(?P<close></(?P<cname>[a-zA-Z]+)\s*>)'
    r'|(?P<selfc><(?P<sname>[a-zA-Z]+)(?:\s[^>]*)?/>)',
    re.DOTALL,
)


def _tokenize(s):
    tokens = []
    pos = 0
    for m in _TAG_RE.finditer(s):
        if m.start() > pos:
            text = s[pos:m.start()]
            if text.strip():
                tokens.append(('text', None, text))
        if m.group('open'):
            tokens.append(('open', m.group('oname').lower(), m.group('open')))
        elif m.group('close'):
            tokens.append(('close', m.group('cname').lower(), m.group('close')))
        else:  # self-closing
            tokens.append(('self', m.group('sname').lower(), m.group('selfc')))
        pos = m.end()
    if pos < len(s):
        tail = s[pos:]
        if tail.strip():
            tokens.append(('text', None, tail))
    return tokens


# ---------------------------------------------------------------------------
# Atom converters
# ---------------------------------------------------------------------------
_OP_MAP = {
    '·': r' \cdot ', '⋅': r' \cdot ', '×': r' \times ', '÷': r' \div ',
    '−': '-', '–': '-', '—': '-',
    '→': r' \to ', '⇒': r' \Rightarrow ', '⇔': r' \Leftrightarrow ',
    '°': r'^{\circ}',
    '≤': r' \leq ', '≥': r' \geq ', '≠': r' \neq ', '≈': r' \approx ',
    '≡': r' \equiv ', '∞': r' \infty ', '±': r' \pm ', '∓': r' \mp ',
    '∝': r' \propto ', '∑': r' \sum ', '∏': r' \prod ', '∫': r' \int ',
    '√': r' \sqrt ', '∈': r' \in ', '∉': r' \notin ',
    '⊂': r' \subset ', '⊆': r' \subseteq ', '∪': r' \cup ', '∩': r' \cap ',
    '∀': r' \forall ', '∃': r' \exists ', '∇': r' \nabla ',
    '∂': r' \partial ', '∆': r' \Delta ',
    '<': ' < ', '>': ' > ', '≪': r' \ll ', '≫': r' \gg ',
    '∼': r' \sim ', '~': r' \sim ',
}

_FUNC_NAMES = {
    'sin', 'cos', 'tan', 'tg', 'ctg', 'cot',
    'arcsin', 'arccos', 'arctan', 'arctg', 'arcctg',
    'log', 'lg', 'ln', 'exp', 'lim', 'min', 'max', 'mod',
    'sh', 'ch', 'th',
}

_GREEK_SINGLE = {
    'α': r'\alpha ', 'β': r'\beta ', 'γ': r'\gamma ', 'δ': r'\delta ',
    'ε': r'\varepsilon ', 'ζ': r'\zeta ', 'η': r'\eta ', 'θ': r'\theta ',
    'ι': r'\iota ', 'κ': r'\kappa ', 'λ': r'\lambda ', 'μ': r'\mu ',
    'ν': r'\nu ', 'ξ': r'\xi ', 'π': r'\pi ', 'ρ': r'\rho ',
    'σ': r'\sigma ', 'τ': r'\tau ', 'φ': r'\varphi ', 'χ': r'\chi ',
    'ψ': r'\psi ', 'ω': r'\omega ',
    'Δ': r'\Delta ', 'Σ': r'\Sigma ', 'Ω': r'\Omega ', 'Φ': r'\Phi ',
    'Θ': r'\Theta ', 'Λ': r'\Lambda ',
}

_COMPOSED = {
    '<=': r' \leq ', '>=': r' \geq ', '!=': r' \neq ',
    '==': r' \equiv ', '**': r' \cdot ',
}


def _convert_op(data):
    d = data.strip()
    if not d:
        return ''
    if d in _OP_MAP:
        return _OP_MAP[d]
    if d.lower() in _FUNC_NAMES:
        return '\\' + d.lower() + ' '
    if d in _COMPOSED:
        return _COMPOSED[d]
    return d  # =, +, -, *, /, (, ), comma, etc.


def _convert_identifier(data):
    d = data.strip()
    if not d:
        return ''
    if len(d) == 1:
        return _GREEK_SINGLE.get(d, d)
    return '\\text{' + d + '}'


# ---------------------------------------------------------------------------
# Recursive-descent parser  (builds a node tree, then renders to LaTeX)
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self):
        self.tokens = []
        self.i = 0

    # -- build tree ---------------------------------------------------------
    def parse(self, tokens):
        self.tokens = tokens
        self.i = 0
        nodes = []
        while self.i < len(self.tokens):
            kind, name, _ = self.tokens[self.i]
            if kind == 'text':
                nodes.append(self.tokens[self.i][2])
                self.i += 1
            elif kind == 'close':
                self.i += 1  # stray close at top level
            else:
                node = self._parse_element()
                if node is not None:
                    nodes.append(node)
        return nodes

    def _parse_element(self):
        kind, name, raw = self.tokens[self.i]
        self.i += 1
        if kind == 'self':
            return {'tag': name, 'kids': [], 'raw': raw}
        kids = []
        while self.i < len(self.tokens):
            kkind, kname, _ = self.tokens[self.i]
            if kkind == 'close' and kname == name:
                self.i += 1
                break
            if kkind == 'close':
                self.i += 1  # mismatched close — skip
                continue
            if kkind == 'text':
                kids.append(self.tokens[self.i][2])
                self.i += 1
            else:
                kids.append(self._parse_element())
        return {'tag': name, 'kids': kids, 'raw': raw}

    # -- render tree → LaTeX ------------------------------------------------
    @staticmethod
    def _is_text(k):
        return isinstance(k, str)

    def render_nodes(self, nodes):
        return ''.join(self.render_node(n) if not self._is_text(n) else n.strip()
                       for n in nodes)

    def render_kids(self, node):
        return self.render_nodes(node['kids'])

    def _text_of(self, kid):
        if self._is_text(kid):
            return kid
        return ''.join(self._text_of(c) for c in kid['kids'])

    def _kids_nonempty(self, node):
        return [k for k in node['kids'] if self._is_text(k) and k.strip()
                or not self._is_text(k)]

    def _render_child(self, kid):
        return kid.strip() if self._is_text(kid) else self.render_node(kid)

    def render_node(self, node):
        tag = node['tag']
        if tag == 'math':
            return self.render_kids(node)
        if tag in ('mrow', 'mstyle', 'merror', 'mpadded'):
            return self.render_kids(node)
        if tag == 'mi':
            return _convert_identifier(self._text_of(node))
        if tag == 'mn':
            return self._text_of(node).strip()
        if tag == 'mo':
            return _convert_op(self._text_of(node))
        if tag == 'mtext':
            return '\\text{' + self._text_of(node).strip() + '}'
        if tag == 'mspace':
            return ' \\, '
        kids = self._kids_nonempty(node)
        if tag == 'mfrac':
            if len(kids) >= 2:
                return '\\frac{' + self._render_child(kids[0]) + '}{' + self._render_child(kids[1]) + '}'
            return self.render_kids(node)
        if tag == 'msqrt':
            return '\\sqrt{' + self.render_kids(node) + '}'
        if tag == 'mroot' and len(kids) >= 2:
            return '\\sqrt[' + self._render_child(kids[1]) + ']{' + self._render_child(kids[0]) + '}'
        if tag == 'msub' and len(kids) >= 2:
            return '{' + self._render_child(kids[0]) + '}_{' + self._render_child(kids[1]) + '}'
        if tag == 'msup' and len(kids) >= 2:
            return '{' + self._render_child(kids[0]) + '}^{' + self._render_child(kids[1]) + '}'
        if tag == 'msubsup' and len(kids) >= 3:
            return ('{' + self._render_child(kids[0]) + '}_{' + self._render_child(kids[1])
                    + '}^{' + self._render_child(kids[2]) + '}')
        if tag == 'mover' and len(kids) >= 2:
            base = self._render_child(kids[0])
            over_raw = self._text_of(kids[1]).strip() if self._is_text(kids[1]) else self._render_child(kids[1])
            if over_raw in ('→', '⃗', '->'):
                return '\\vec{' + base + '}'
            if over_raw in ('¯', '-', '‾', '−'):
                return '\\overline{' + base + '}'
            if over_raw == '^':
                return '\\hat{' + base + '}'
            if over_raw == '.':
                return '\\dot{' + base + '}'
            return '\\overset{' + over_raw + '}{' + base + '}'
        if tag == 'munder' and len(kids) >= 2:
            return '{' + self._render_child(kids[0]) + '}_{' + self._render_child(kids[1]) + '}'
        if tag == 'mfenced':
            attrs = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', node.get('raw', '')))
            o = attrs.get('open', '(')
            c = attrs.get('close', ')')
            return o + self.render_kids(node) + c
        # Unknown tag — render its children
        return self.render_kids(node)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
_MATH_BLOCK_RE = re.compile(r'<math\b[^>]*>.*?</math>', re.DOTALL)
_MATH_BLOCK_RE_SELF = re.compile(r'<math\b[^>]*/>', re.DOTALL)


def convert_single_math(mathml_str):
    r"""Convert one ``<math>...</math>`` block into inline LaTeX ``\( ... \)``."""
    tokens = _tokenize(mathml_str)
    nodes = _Parser().parse(tokens)
    latex = _Parser().render_nodes(nodes)
    latex = re.sub(r'[ \t]{2,}', ' ', latex).strip()
    if not latex:
        return ''
    return '\\( ' + latex + ' \\)'


def mathml_to_latex(text):
    """Replace every ``<math>...</math>`` block in *text* with inline LaTeX.

    Non-MathML text is left untouched so the caller can post-process HTML.
    The ``<span class="math-chip">`` wrapper is transparent — only ``<math>``
    blocks are converted.
    """
    if '<math' not in text:
        return text

    text = _MATH_BLOCK_RE.sub(lambda m: convert_single_math(m.group(0)), text)
    text = _MATH_BLOCK_RE_SELF.sub('', text)
    return text
