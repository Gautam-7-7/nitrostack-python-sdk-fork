import os
import pytest
from nitrostack.ui_next import compile_next_widget

def test_next_widget_compilation():
    # Target starter widgets folder
    starter_widgets_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../nitrostack/templates/starter/src/widgets")
    )
    
    # Compile the calculator-result widget
    compiled_html = compile_next_widget(
        project_dir=starter_widgets_dir,
        route_path="calculator-result"
    )
    
    # Assertions
    assert compiled_html is not None
    assert "<html" in compiled_html.lower() or "<!doctype html" in compiled_html.lower()
    
    # Check that javascript is inlined (script tags exist and no external script targets)
    assert "<script>" in compiled_html or "<script " in compiled_html
    assert 'src="/_next/' not in compiled_html
    assert 'href="/_next/static/css/' not in compiled_html
