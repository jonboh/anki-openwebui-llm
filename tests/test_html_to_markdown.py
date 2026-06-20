r"""Tests for _html_to_markdown — standalone copy matching the plugin code."""
import html
import re

# Pure-function copy matching the live _html_to_markdown on eva/open-webui-integration
def _html_to_markdown(raw: str) -> str:
    if not raw:
        return ""
    text = raw
    # 1. Fenced code blocks
    text = re.sub(
        r"<pre[^>]*>\s*<code[^>]*class=\"language-(\w+)\"[^>]*>(.*?)</code>\s*</pre>",
        r"\n```\1\n\2\n```\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(
        r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>",
        r"\n```\n\1\n```\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(
        r"<pre[^>]*>(.*?)</pre>",
        r"\n```\n\1\n```\n", text, flags=re.IGNORECASE | re.DOTALL)
    # 2. Line-break tags
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|li|tr)[^>]*>\s*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?ul[^>]*>|</?ol[^>]*>\s*", "\n", text, flags=re.IGNORECASE)
    # 2.5 Block math — both <anki-mathjax block="true"> and literal \[...\]
    text = re.sub(
        r'<anki-mathjax\s+block\s*=\s*["\']true["\'][^>]*>(.*?)</anki-mathjax>',
        r"\n\n\1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(
        r'\s*\\\[(.+?)\\\]\s*',
        lambda m: f'\n\n\\[{m.group(1)}\\]\n\n',
        text, flags=re.DOTALL)
    # 2.6 Inline math
    text = re.sub(
        r'<anki-mathjax>(.*?)</anki-mathjax>',
        r'\1', text, flags=re.IGNORECASE | re.DOTALL)
    # 3. Inline formatting
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    # 4. Inline code
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.IGNORECASE | re.DOTALL)
    # 5. Cleanup
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty():
    assert _html_to_markdown("") == ""
    assert _html_to_markdown(None) == ""


def test_plain_text_passthrough():
    assert _html_to_markdown("hello world") == "hello world"
    assert _html_to_markdown("  spaced  ") == "spaced"


def test_bold_italic():
    r = _html_to_markdown("<b>Bold</b> <i>Italic</i>")
    assert "**Bold**" in r
    assert "*Italic*" in r


def test_strong_em():
    r = _html_to_markdown("<strong>Str</strong> <em>Em</em>")
    assert "**Str**" in r
    assert "*Em*" in r


def test_br_to_paragraph_break():
    r = _html_to_markdown("line1<br>line2")
    # Should have a paragraph break between lines
    assert "line1" in r and "line2" in r
    assert "\n\n" in r or r.count("\n") >= 1


def test_br_self_closing():
    r = _html_to_markdown("a<br/>b")
    assert "\n\n" in r or r.count("\n") >= 1


def test_br_with_space():
    r = _html_to_markdown("a<br />b")
    assert "\n\n" in r or r.count("\n") >= 1


def test_html_entities():
    r = _html_to_markdown("a &amp; b &lt; c &gt; d")
    assert "a & b" in r
    assert "< c" in r
    assert "> d" in r


def test_nbsp():
    r = _html_to_markdown("hello&nbsp;world")
    # \xa0 is non-breaking space
    assert "\xa0" in r or "hellonbspworld" in r


def test_inline_code():
    r = _html_to_markdown("<code>var x = 1</code>")
    assert "`var x = 1`" in r


def test_fenced_code_with_language():
    raw = '<pre><code class="language-python">print("hi")</code></pre>'
    r = _html_to_markdown(raw)
    assert "```python" in r
    assert 'print("hi")' in r
    assert "```" in r


def test_fenced_code_without_language():
    raw = "<pre><code>print('hi')</code></pre>"
    r = _html_to_markdown(raw)
    assert "```" in r
    assert "print('hi')" in r


def test_bare_pre():
    raw = "<pre>monospace text</pre>"
    r = _html_to_markdown(raw)
    assert "```" in r
    assert "monospace text" in r


def test_p_tag_to_newline():
    r = _html_to_markdown("<p>para1</p><p>para2</p>")
    assert "para1" in r
    assert "para2" in r


def test_list_tags():
    r = _html_to_markdown("<ul><li>item1</li><li>item2</li></ul>")
    assert "item1" in r
    assert "item2" in r


def test_inline_anki_mathjax_stripped():
    r = _html_to_markdown("<anki-mathjax> E = mc^2 </anki-mathjax>")
    assert "E = mc^2" in r
    assert "<anki-mathjax>" not in r


def test_block_math_anki_tag_isolated():
    r"""<anki-mathjax block="true"> content gets \n\n padding."""
    raw = (
        'Specifically: '
        '<anki-mathjax block="true"> g\' = g \\circ (h \\times \\text{id}_a) </anki-mathjax>'
        ' where'
    )
    r = _html_to_markdown(raw)
    assert "<anki-mathjax" not in r
    assert "g' = g" in r
    lines = r.split("\n")
    math_line = None
    for i, line in enumerate(lines):
        if "g'" in line and "circ" in line:
            math_line = i
            break
    assert math_line is not None, "Block math content not found in output"
    # Should have blank line before and after
    if math_line > 0:
        assert lines[math_line - 1].strip() == ""
    if math_line < len(lines) - 1:
        assert lines[math_line + 1].strip() == ""


def test_literal_display_math_isolated():
    r"""Literal \[...\] in the input gets \n\n padding."""
    raw = r"before \[ x^2 \] after"
    r = _html_to_markdown(raw)
    assert r"\[ x^2 \]" in r
    lines = r.split("\n")
    math_idx = None
    for i, line in enumerate(lines):
        if "x^2" in line:
            math_idx = i
            break
    assert math_idx is not None, "Display math not found in output"
    if math_idx > 0:
        assert lines[math_idx - 1].strip() == ""
    if math_idx < len(lines) - 1:
        assert lines[math_idx + 1].strip() == ""


def test_adjunction_card_real():
    r"""Real-world adjunction card with <br> and bold (raw strings for LaTeX)."""
    raw = (
        r"An adjunction between categories \( C \) and \( D \) is "
        r"a pair of functors \( L: D \to C \) and \( R: C \to D \) "
        r"equipped with two natural transformations:"
        r"<br>1. <b>Unit</b> \( \eta: \text{Id}_D \to R \circ L \) "
        r"<br>2. <b>Counit</b> \( \varepsilon: L \circ R \to \text{Id}_C \)"
    )
    r = _html_to_markdown(raw)
    assert "**Unit**" in r
    assert "**Counit**" in r
    assert r"\eta" in r or r"\\eta" in r
    assert r"\text" in r or r"\\text" in r


def test_ranking_card_literal():
    r"""Ranking card with literal \[...\] display math (Anki-processed form)."""
    raw = (
        r"\( z \) is \"better\" than \( z' \) if there exists "
        r"a unique morphism \( h: z' \to z \) such that the evaluation on "
        r"\( z' \) factors through the evaluation on \( z \). "
        r"Specifically: \[ g' = g \circ (h \times \text{id}_a) \] "
        r"where \( g': z' \times a \to b \) and \( g: z \times a \to b \)."
    )
    r = _html_to_markdown(raw)
    # Display math content present
    assert "g'" in r
    assert r"\circ" in r or r"\\circ" in r
    # Should be isolated with blank lines
    lines = r.split("\n")
    dm_idx = None
    for i, line in enumerate(lines):
        if "g'" in line and ("circ" in line or "text" in line):
            dm_idx = i
            break
    assert dm_idx is not None, "Display math not found"
    if dm_idx > 0:
        assert lines[dm_idx - 1].strip() == ""
    if dm_idx < len(lines) - 1:
        assert lines[dm_idx + 1].strip() == ""


def test_ranking_card_anki_tag():
    r"""Ranking card with <anki-mathjax block="true"> tag (raw Anki form)."""
    raw = (
        r"\( z \) is \"better\" than \( z' \) if there exists "
        r"a unique morphism \( h: z' \to z \) such that the evaluation on "
        r"\( z' \) factors through the evaluation on \( z \). "
        r"Specifically: <anki-mathjax block=\"true\"> g' = g \circ (h \times \text{id}_a) </anki-mathjax>"
        r"where \( g': z' \times a \to b \) and \( g: z \times a \to b \)."
    )
    r = _html_to_markdown(raw)
    assert "<anki-mathjax" not in r
    assert "g'" in r
    lines = r.split("\n")
    dm_idx = None
    for i, line in enumerate(lines):
        if "g'" in line and ("circ" in line or "text" in line):
            dm_idx = i
            break
    assert dm_idx is not None, "Block math content not found"
    if dm_idx > 0:
        assert lines[dm_idx - 1].strip() == ""
    if dm_idx < len(lines) - 1:
        assert lines[dm_idx + 1].strip() == ""


def test_img_tag_stripped():
    r = _html_to_markdown('text<br><img src="x.png">more')
    assert "x.png" not in r


def test_mixed_content():
    r"""Bold, inline math, br, all together."""
    raw = (
        "<b>Q:</b> solve "
        "<anki-mathjax> x^2 </anki-mathjax>"
        "<br><br>done"
    )
    r = _html_to_markdown(raw)
    assert "**Q:**" in r
    assert "x^2" in r
    assert "<anki-mathjax>" not in r
    assert "\n\n" in r


def test_triple_br_normalized():
    r = _html_to_markdown("a<br><br><br>b")
    # Three <br> → 3 * \n\n = 6 newlines → normalized to max \n\n
    assert r.count("\n") <= 4


def test_html_tag_stripping():
    r = _html_to_markdown("<div><span class='x'>hello</span></div>")
    assert "hello" in r
    assert "<div>" not in r
    assert "<span" not in r


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        ("empty", test_empty),
        ("plain_text", test_plain_text_passthrough),
        ("bold_italic", test_bold_italic),
        ("strong_em", test_strong_em),
        ("br_to_paragraph", test_br_to_paragraph_break),
        ("br_self_closing", test_br_self_closing),
        ("br_with_space", test_br_with_space),
        ("html_entities", test_html_entities),
        ("nbsp", test_nbsp),
        ("inline_code", test_inline_code),
        ("fenced_code_with_lang", test_fenced_code_with_language),
        ("fenced_code_no_lang", test_fenced_code_without_language),
        ("bare_pre", test_bare_pre),
        ("p_tag", test_p_tag_to_newline),
        ("list_tags", test_list_tags),
        ("inline_anki_mathjax", test_inline_anki_mathjax_stripped),
        ("block_math_anki_tag", test_block_math_anki_tag_isolated),
        ("literal_display_math", test_literal_display_math_isolated),
        ("adjunction_card", test_adjunction_card_real),
        ("ranking_card_literal", test_ranking_card_literal),
        ("ranking_card_anki_tag", test_ranking_card_anki_tag),
        ("img_tag", test_img_tag_stripped),
        ("mixed_content", test_mixed_content),
        ("triple_br", test_triple_br_normalized),
        ("tag_stripping", test_html_tag_stripping),
    ]

    passed = 0
    failed = []
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  \u2713 {name}")
        except AssertionError as e:
            failed.append(name)
            msg = str(e) if e else "assertion failed"
            print(f"  \u2717 {name}: {msg}")
        except Exception as e:
            failed.append(name)
            print(f"  \u2717 {name}: {type(e).__name__}: {e}")

    total = len(tests)
    print(f"\n{'=' * 50}")
    print(f"{passed}/{total} passed")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
