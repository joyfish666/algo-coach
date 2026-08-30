"""Statement HTML -> Markdown conversion.

Self-authored converter covering the tag subset leetcode.cn statements use.
Output is regenerable program input: workspaces record which converter version
produced their statement.md (meta.json ``statement_version``) and stale files
are re-generated from a fresh detail fetch (see lc.workspace.STATEMENT_VERSION).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _HTMLToMarkdown(HTMLParser):
    _HEADINGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}
    _BLOCK_END = {"p", "div", "blockquote"} | set(_HEADINGS)

    # Sentence-level punctuation that cn statements put INSIDE a bold segment
    # right before more text ("**进阶：**你可以想出…"). CommonMark's flanking
    # rules refuse to close a delimiter run preceded by punctuation and
    # followed by a letter, so those markers would leak into the rendered
    # page as literal "**". The punctuation is moved outside the markers -
    # a purely cosmetic boundary shift (the characters are unchanged).
    _TRAIL_PUNCT = set("：:，,、。．；;！!？?")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        # blocks entries are (markdown_text, is_table_row) pairs; the flag
        # drives the joiner (table rows share one newline, blocks get blank
        # lines) so a table renders as one GFM table instead of paragraphs
        self.blocks = []
        self.buf = []
        self.pending_prefix = ""
        self.list_stack = []  # entries: {"ordered": bool, "n": int}
        self.in_table = False
        self.row_cols = 0  # cells seen in the row being accumulated
        self.table_header_done = False
        self.pre_lines = None
        self.pre_language = ""
        self.link_stack = []
        # buf indices of the currently-open bold/italic markers; closing
        # rebuilds the whole wrapped segment so emphasis markers stay
        # CommonMark-renderable instead of being concatenated blindly
        self.bold_stack = []
        self.em_stack = []
        # buf indices of open inline-code backticks; emphasis nested inside
        # a code span cannot render, so its markers are dropped on close
        self.code_stack = []

    def flush_block(self):
        text = "".join(self.buf).strip()
        if text:
            self.blocks.append((self.pending_prefix + text, False))
        self.buf = []
        # markers never span blocks; a malformed open would otherwise leak a
        # stale buf index into the next paragraph
        self.bold_stack.clear()
        self.em_stack.clear()
        self.code_stack.clear()
        self.pending_prefix = ""

    @staticmethod
    def _attr(attrs, name):
        for key, value in attrs:
            if key == name:
                return value or ""
        return ""

    def flush_row(self):
        """Close the accumulating buffer as one GFM table-row line.

        Rows flushed as standalone blocks rendered as literal paragraphs in
        markdown-it: tag-gap whitespace made the first cell emit a leading
        "|" separator, no delimiter row existed, and blank lines between
        rows broke the table. A full pipe row plus a delimiter row after
        the first one renders as a real table; the leading/trailing pipes
        also keep single-column tables parseable.
        """
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        self.bold_stack.clear()
        self.em_stack.clear()
        self.code_stack.clear()
        self.pending_prefix = ""
        if not text:
            return
        self.blocks.append((f"| {text} |", True))
        if not self.table_header_done:
            self.table_header_done = True
            delimiter = "| " + " | ".join(["---"] * max(self.row_cols, 1)) + " |"
            self.blocks.append((delimiter, True))

    def _close_wrap(self, stack, marker):
        """Close a bold/italic segment as CommonMark-renderable markdown.

        Concatenating markers blindly produced literal "**" garbage on cn
        statements: trailing whitespace inside the wrap ("**和为目标值 **"
        - the closer is no longer right-flanking), sentence punctuation
        before the closer ("**进阶：**你" - flanking rules refuse to close
        a run preceded by punctuation and followed by a letter), and empty
        wraps. The wrapped segment is rebuilt with those normalized:
        whitespace/punctuation move outside the markers, characters are
        unchanged.
        """
        start = stack.pop() if stack else None
        if start is None or start >= len(self.buf):
            return  # close without a matching open in this block
        if self.code_stack and self.code_stack[-1] < start:
            # the emphasis opened inside an inline code span ("<code><strong>
            # 1</strong></code>"): markers inside backticks render as literal
            # asterisks, so the emphasis is dropped (the code font already
            # reads as emphasis); the open marker was already appended
            del self.buf[start]
            return
        inner = "".join(self.buf[start + 1:])
        del self.buf[start:]
        self.buf.extend(self._balanced_wrap(inner, marker))

    def _balanced_wrap(self, inner, marker):
        lead = inner[: len(inner) - len(inner.lstrip())]
        trail = inner[len(inner.rstrip()):]
        core = inner.strip()
        if not core:
            return [lead, trail]
        moved = ""
        while core and core[-1] in self._TRAIL_PUNCT:
            moved = core[-1] + moved
            core = core[:-1]
        if not core:
            # the whole segment was punctuation ("**：**"): nothing to wrap
            return [lead, moved, trail]
        pieces = [lead, marker, core, marker, moved, trail]
        if not lead and self.buf and self.buf[-1].endswith("*"):
            # two wrapped segments glued together ("**a***b*") form an
            # ambiguous delimiter run; a separator keeps both renderable
            pieces.insert(0, " ")
        return pieces

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self.flush_block()
            classes = self._attr(attrs, "class")
            match = re.search(r"language-([\w+#-]+)", classes)
            self.pre_language = match.group(1) if match else ""
            self.pre_lines = []
            return
        if tag == "code" and self.pre_lines is not None and not self.pre_language:
            classes = self._attr(attrs, "class")
            match = re.search(r"language-([\w+#-]+)", classes)
            if match:
                self.pre_language = match.group(1)
            return
        if self.pre_lines is not None:
            # inside a fenced block every tag is literal content: cn wraps the
            # 输入：/输出： labels in <strong>, and emitting markers for them
            # appended to the PARAGRAPH buffer (not pre_lines), resurfacing as
            # "************" runs in front of the next heading
            if tag == "br":
                self.pre_lines.append("\n")
            return
        if tag == "br":
            self.buf.append("\n")
            return
        if tag in ("ul", "ol"):
            if self.in_table:
                return  # list markup inside a cell stays inline text
            self.flush_block()
            self.list_stack.append({"ordered": tag == "ol", "n": 0})
            return
        if tag == "li":
            if self.in_table:
                return
            self.flush_block()
            level = self.list_stack[-1] if self.list_stack else {"ordered": False, "n": 0}
            if level["ordered"]:
                level["n"] += 1
                self.buf.append(f"{level['n']}. ")
            else:
                self.buf.append("- ")
            return
        if tag in self._HEADINGS:
            if self.in_table:
                return
            self.flush_block()
            self.pending_prefix = self._HEADINGS[tag]
            return
        if tag in ("strong", "b"):
            self.bold_stack.append(len(self.buf))
            self.buf.append("**")
            return
        if tag in ("em", "i"):
            self.em_stack.append(len(self.buf))
            self.buf.append("*")
            return
        if tag == "code" and self.pre_lines is None:
            self.buf.append("`")
            self.code_stack.append(len(self.buf) - 1)
            return
        if tag == "sup":
            self.buf.append("^")
            return
        if tag == "tr":
            if self.in_table:
                # malformed row without a closing </tr> must not merge rows
                self.flush_row()
            self.row_cols = 0
            return
        if tag in ("td", "th"):
            if not self.in_table:
                return
            if any(s.strip() for s in self.buf):
                self.buf.append(" | ")
            self.row_cols += 1
            return
        if tag == "table":
            self.flush_block()
            self.in_table = True
            self.table_header_done = False
            return
        if tag == "a":
            href = self._attr(attrs, "href") or ""
            self.buf.append("[")
            self.link_stack.append(href)
            return
        if tag == "img":
            src = self._attr(attrs, "src") or ""
            alt = self._attr(attrs, "alt") or ""
            self.buf.append(f"![{alt}]({src})")
            return

    def handle_endtag(self, tag):
        if self.pre_lines is not None and tag != "pre":
            # literal content inside a fence (see handle_starttag): the
            # closing </strong> of "输出：" must not emit a marker here
            return
        if tag == "pre":
            code = "".join(self.pre_lines).strip("\n")
            fence = f"```{self.pre_language}" if self.pre_language else "```"
            self.blocks.append((f"{fence}\n{code}\n```", False))
            self.pre_lines = None
            self.pre_language = ""
            return
        if tag in ("strong", "b"):
            self._close_wrap(self.bold_stack, "**")
            return
        if tag in ("em", "i"):
            self._close_wrap(self.em_stack, "*")
            return
        if tag == "code" and self.pre_lines is None:
            self.buf.append("`")
            if self.code_stack:
                self.code_stack.pop()
            return
        if tag == "a":
            href = self.link_stack.pop() if self.link_stack else ""
            label = "".join(self.buf).strip()
            self.buf = [label + f"]({href})" if href else label + "]"]
            return
        if tag == "li":
            if self.in_table:
                return
            self.flush_block()
            return
        if tag in ("ul", "ol"):
            if self.in_table:
                return
            self.flush_block()
            if self.list_stack:
                self.list_stack.pop()
            return
        if tag == "table":
            self.in_table = False
            self.flush_row()
            return
        if tag == "tr" and self.in_table:
            self.flush_row()
            return
        if tag in self._BLOCK_END:
            if self.in_table:
                return  # cell content stays on one row line
            self.flush_block()

    def handle_data(self, data):
        if self.pre_lines is not None:
            self.pre_lines.append(data)
            return
        collapsed = re.sub(r"[ \t\r\f\v]+", " ", data.replace("\n", " "))
        if self.in_table:
            # an unescaped pipe would split the cell; GFM honors "\|" even
            # inside inline code spans
            collapsed = collapsed.replace("|", "\\|")
        self.buf.append(collapsed)

    def close(self):
        super().close()
        self.flush_block()


def html_to_markdown(html_text: str) -> str:
    """Convert leetcode statement HTML into plain markdown-ish text.

    Formulas stay as raw text (sup/sub flattened); images keep markdown
    syntax so they render online and visibly break offline (documented
    v0.1 limitation).
    """
    parser = _HTMLToMarkdown()
    parser.feed(html_text or "")
    parser.close()
    # consecutive table-row blocks share one newline so the whole table is
    # a single GFM table; everything else keeps blank-line paragraph joins
    parts = []
    prev_row = False
    for text, is_row in parser.blocks:
        text = text.strip()
        if not text:
            continue
        if parts:
            parts.append("\n" if (is_row and prev_row) else "\n\n")
        parts.append(text)
        prev_row = is_row
    joined = "".join(parts)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip() + ("\n" if joined else "")
