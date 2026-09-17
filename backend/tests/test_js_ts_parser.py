from app.services.ingestion.parser.js_ts_parser import parse_js_ts

SAMPLE = """
const express = require('express');
import { Router } from 'express';

function standaloneFunction(x) {
  return x + 1;
}

const arrowConst = (a, b) => {
  return a + b;
};

var app = exports = module.exports = {};

app.init = function init() {
  return true;
};

app.use = function use(fn) {
  return fn;
};

Something.prototype.method = function () {
  return 1;
};

class Widget {
  render() {
    return 1;
  }
}

router.get('/users/:id', function (req, res) {
  res.send('ok');
});
"""


def test_extracts_standalone_function():
    result = parse_js_ts(SAMPLE)
    assert any(s.name == "standaloneFunction" and s.symbol_type == "function" for s in result.symbols)


def test_extracts_arrow_const():
    result = parse_js_ts(SAMPLE)
    assert any(s.name == "arrowConst" and s.symbol_type == "function" for s in result.symbols)


def test_extracts_property_assignment_function():
    """Regression test: found live during testing against expressjs/express
    -- a 632-line real file (lib/application.js) yielded only 2 symbols
    because this extremely common prototypal-style pattern
    (`app.method = function name() {}`) wasn't recognized at all."""
    result = parse_js_ts(SAMPLE)
    names = {s.name for s in result.symbols if s.symbol_type == "method"}
    assert "init" in names
    assert "use" in names


def test_extracts_prototype_assignment_function():
    result = parse_js_ts(SAMPLE)
    names = {s.name for s in result.symbols if s.symbol_type == "method"}
    assert "method" in names


def test_extracts_class_and_method():
    result = parse_js_ts(SAMPLE)
    assert any(s.name == "Widget" and s.symbol_type == "class" for s in result.symbols)
    assert any(s.name == "render" and s.parent_name == "Widget" for s in result.symbols)


def test_extracts_route():
    result = parse_js_ts(SAMPLE)
    routes = [s for s in result.symbols if s.symbol_type == "route"]
    assert any(r.route_path == "/users/:id" and r.http_method == "GET" for r in routes)


def test_extracts_imports():
    result = parse_js_ts(SAMPLE)
    raws = {i.raw for i in result.imports}
    assert "express" in raws
