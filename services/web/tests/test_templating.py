"""Pure web tests: no api, no shared-core."""

import pytest

from web.templating import (
    MissingVariable,
    escape_html,
    render,
    render_rows,
    variables_in,
)


def test_variables_in_preserves_order_and_dedupes():
    assert variables_in("{{ a }} {{b}} {{ a }} {{ c_1 }}") == ["a", "b", "c_1"]
    assert variables_in("no placeholders") == []


def test_render_substitutes():
    assert render("Hello {{ name }}!", {"name": "Peas"}) == "Hello Peas!"
    assert render("{{a}}{{a}}", {"a": 1}) == "11"


def test_render_autoescapes_by_default():
    assert render("{{ x }}", {"x": "<b>&</b>"}) == "&lt;b&gt;&amp;&lt;/b&gt;"
    assert render("{{ x }}", {"x": "<b>"}, autoescape=False) == "<b>"


def test_render_reports_every_missing_variable():
    with pytest.raises(MissingVariable) as exc:
        render("{{ a }} {{ b }} {{ c }}", {"b": 1})
    assert "a" in str(exc.value) and "c" in str(exc.value)


def test_render_type_check():
    with pytest.raises(TypeError):
        render(None, {})


def test_extra_context_keys_are_ignored():
    assert render("{{ a }}", {"a": 1, "unused": 2}) == "1"


def test_escape_html_covers_all_five_entities():
    assert escape_html("""<&>"'""") == "&lt;&amp;&gt;&quot;&#39;"
    assert escape_html(42) == "42"


def test_escape_html_does_not_double_escape_ampersands_it_just_added():
    # & is replaced first, so <  ->  &lt;  and not  &amp;lt;
    assert escape_html("<") == "&lt;"


def test_render_rows():
    rows = [{"n": 1}, {"n": 2}, {"n": 3}]
    assert render_rows("row {{ n }}", rows) == "row 1\nrow 2\nrow 3"
    assert render_rows("row {{ n }}", rows, separator=", ") == "row 1, row 2, row 3"
    assert render_rows("row {{ n }}", []) == ""
