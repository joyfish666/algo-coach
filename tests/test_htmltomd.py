"""Statement HTML -> Markdown converter (lc.htmltomd)."""

from lc.htmltomd import html_to_markdown


def test_html_paragraphs_and_inline_marks():
    html = "<p>Hello <strong>world</strong> and <em>grace</em></p>"
    md = html_to_markdown(html)
    assert "Hello **world** and *grace*" in md


def test_html_pre_block_becomes_fence():
    html = '<pre><code>int x = 1;\nfoo(x);</code></pre>'
    md = html_to_markdown(html)
    assert "```\nint x = 1;\nfoo(x);\n```" in md


def test_html_pre_with_language_class():
    html = '<pre><code class="language-cpp">auto v = 1;</code></pre>'
    md = html_to_markdown(html)
    assert "```cpp\nauto v = 1;\n```" in md


def test_html_list_items():
    html = "<ul><li>first</li><li>second</li></ul>"
    md = html_to_markdown(html)
    assert "- first" in md
    assert "- second" in md


def test_html_ordered_list_numbers_items():
    html = "<ol><li>one</li><li>two</li><li>three</li></ol>"
    lines = [line for line in html_to_markdown(html).splitlines() if line.strip()]
    assert lines == ["1. one", "2. two", "3. three"]


def test_html_nested_ordered_lists_restart_numbering():
    html = "<ol><li>a<ol><li>x</li><li>y</li></ol></li><li>b</li></ol>"
    md = html_to_markdown(html)
    assert "1. a" in md
    assert "1. x" in md
    assert "2. y" in md
    assert "2. b" in md


def test_html_table_cells_keep_separator():
    html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
    md = html_to_markdown(html)
    assert "a | b" in md
    assert "c | d" in md


def test_html_formula_superscript_stays_raw():
    html = "<p>x<sup>2</sup> + y<sub>1</sub> &lt; 3</p>"
    md = html_to_markdown(html)
    assert "x^2 + y1 < 3" in md


def test_html_link_and_image():
    html = '<p>see <a href="https://a.b">doc</a></p><img src="https://img/1.png" alt="pic">'
    md = html_to_markdown(html)
    assert "[doc](https://a.b)" in md
    assert "![pic](https://img/1.png)" in md


def test_html_empty_input():
    assert html_to_markdown("") == ""


def test_html_strong_inside_pre_stays_literal():
    """cn wraps the 输入：/输出： labels in <strong> inside <pre>. Emitting
    markers for them appended to the PARAGRAPH buffer (not the fence lines)
    and resurfaced as "************" runs before the next heading."""
    html = (
        "<p><strong>示例 1：</strong></p>"
        "<pre><strong>输入：</strong>nums = [2,7,11,15]\n<strong>输出：</strong>[0,1]</pre>"
        "<p><strong>示例 2：</strong></p>"
    )
    md = html_to_markdown(html)
    assert "********" not in md
    fence = md.split("```")[1]
    assert "输入：nums = [2,7,11,15]" in fence
    assert "**" not in fence
    assert "**示例 2**：" in md


def test_html_strong_trailing_cjk_punctuation_stays_renderable():
    """CommonMark flanking rules refuse to close "**进阶：**你" (punctuation
    before the closer, letter after) - the markers used to leak as literal
    "**" in the rendered statement. Punctuation moves outside the markers."""
    html = "<p><strong>进阶：</strong>你可以想出更快的算法吗？</p>"
    md = html_to_markdown(html)
    assert md.strip() == "**进阶**：你可以想出更快的算法吗？"


def test_html_strong_inner_whitespace_moved_outside():
    html = "<p><strong>和为目标值 </strong><em><code>target</code></em></p>"
    md = html_to_markdown(html)
    # trailing space inside the wrap broke the closer; it moves outside, and
    # the whitespace keeps the two adjacent runs unambiguous
    assert md.strip() == "**和为目标值** *`target`*"


def test_html_empty_strong_dropped():
    html = "<p>a<strong></strong>b</p>"
    md = html_to_markdown(html)
    assert "****" not in md
    assert "ab" in md
