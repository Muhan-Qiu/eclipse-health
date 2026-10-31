"""契约 v2 schema 测试：受控 UI 贡献、工具定义与向后兼容。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from eclipse_health_backend.modules.errors import ModuleError
from eclipse_health_backend.modules.manifest import load_manifest_file, parse_manifest

ROOT = Path(__file__).resolve().parents[3]
DEMO_MANIFEST = json.loads((ROOT / "modules" / "demo.echo" / "module.json").read_text(encoding="utf-8"))

WIDGET = {
    "id": "weight-trend",
    "title": "体重趋势",
    "description": "",
    "size": "md",
    "dataSource": {"type": "module-rpc", "method": "stats", "params": {"days": 30}},
    "view": {"type": "sparkline", "unit": "kg", "valuePath": "latest.weight"},
}

PAGE = {
    "id": "weight",
    "title": "体重",
    "icon": "scale",
    "layout": [
        {"component": "text", "text": "最近 30 天"},
        {
            "component": "table",
            "source": {"type": "module-rpc", "method": "list"},
            "rowPath": "items",
            "columns": [
                {"key": "capturedAt", "label": "时间"},
                {"key": "weight", "label": "体重", "unit": "kg"},
            ],
        },
        {
            "component": "list",
            "source": {"type": "module-rpc", "method": "list"},
            "itemPath": "items",
            "primaryPath": "label",
        },
        {"component": "detail", "source": {"type": "module-rpc", "method": "latest"}},
        {
            "component": "form",
            "title": "新增",
            "source": {"type": "module-rpc", "method": "defaults"},
            "submitMethod": "create",
            "fields": [
                {"key": "weight", "label": "体重", "type": "number", "required": True},
                {
                    "key": "mood",
                    "label": "状态",
                    "type": "select",
                    "options": [{"value": "ok", "label": "正常"}],
                },
            ],
        },
    ],
}

TOOL = {
    "id": "demo.echo",
    "name": "Echo",
    "description": "Echo text back.",
    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    "longRunning": False,
}


def _manifest(**overrides):
    data = copy.deepcopy(DEMO_MANIFEST)
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def _widget_manifest(widget: dict | None = None):
    return _manifest(
        type="dashboard-widget",
        contributes={"ui": {"widgets": [copy.deepcopy(widget or WIDGET)]}},
    )


def _page_manifest(page: dict | None = None):
    return _manifest(
        type="health-domain",
        contributes={"ui": {"pages": [copy.deepcopy(page or PAGE)]}},
    )


def _bad_form_field_type(page: dict) -> None:
    page["layout"][4]["fields"][0]["type"] = "color"


def test_widget_and_page_manifests_pass() -> None:
    widget_manifest = parse_manifest(_widget_manifest())
    widget = widget_manifest.contributes["ui"]["widgets"][0]
    assert widget["view"]["type"] == "sparkline"
    assert widget["dataSource"]["method"] == "stats"

    page_manifest = parse_manifest(_page_manifest())
    page = page_manifest.contributes["ui"]["pages"][0]
    assert [block["component"] for block in page["layout"]] == [
        "text",
        "table",
        "list",
        "detail",
        "form",
    ]


def test_widget_internal_link_passes() -> None:
    widget = copy.deepcopy(WIDGET)
    widget["link"] = "/modules/io.github.example.weight-trend/pages/weight?tab=1"
    manifest = parse_manifest(_widget_manifest(widget))
    assert manifest.contributes["ui"]["widgets"][0]["link"].startswith("/modules/")


@pytest.mark.parametrize(
    "link",
    [
        "https://example.com/weight",
        "//example.com/weight",
        "/../admin",
        "/a/../b",
        "/a//b",
        "modules/weight",
        "/a\\b",
        "/a b",
        "/a://b",
        "",
    ],
    ids=[
        "absolute-url",
        "protocol-relative",
        "leading-dotdot",
        "inner-dotdot",
        "double-slash",
        "missing-leading-slash",
        "backslash",
        "whitespace",
        "embedded-protocol",
        "empty",
    ],
)
def test_invalid_widget_links_are_rejected(link: str) -> None:
    widget = copy.deepcopy(WIDGET)
    widget["link"] = link
    with pytest.raises(ModuleError) as info:
        parse_manifest(_widget_manifest(widget))
    assert info.value.code == "INVALID_INPUT"


def test_page_value_formats_pass() -> None:
    page = copy.deepcopy(PAGE)
    page["layout"][1]["columns"][0]["format"] = "datetime"
    page["layout"][1]["columns"][1]["format"] = "number"
    page["layout"][3]["fields"] = [
        {"key": "capturedAt", "label": "时间", "format": "date"}
    ]
    page["layout"][4]["fields"][0]["format"] = "number"
    page["layout"][4]["fields"][1]["format"] = "text"

    manifest = parse_manifest(_page_manifest(page))
    layout = manifest.contributes["ui"]["pages"][0]["layout"]
    assert layout[1]["columns"][0]["format"] == "datetime"
    assert layout[3]["fields"][0]["format"] == "date"
    assert layout[4]["fields"][0]["format"] == "number"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda page: page["layout"][1]["columns"][0].update(format="currency"),
        lambda page: page["layout"][3].update(
            fields=[{"key": "at", "label": "时间", "format": "currency"}]
        ),
        lambda page: page["layout"][4]["fields"][0].update(format="currency"),
    ],
    ids=["bad-column-format", "bad-detail-format", "bad-form-format"],
)
def test_invalid_page_formats_are_rejected(mutate) -> None:
    page = copy.deepcopy(PAGE)
    mutate(page)
    with pytest.raises(ModuleError) as info:
        parse_manifest(_page_manifest(page))
    assert info.value.code == "INVALID_INPUT"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda widget: widget.pop("title"),
        lambda widget: widget.pop("size"),
        lambda widget: widget.update(size="xl"),
        lambda widget: widget.update(view={"type": "iframe", "valuePath": "url"}),
        lambda widget: widget.update(title="x" * 121),
        lambda widget: widget["view"].pop("valuePath"),
        lambda widget: widget["view"].update(valuePath="$.latest.weight"),
        lambda widget: widget["dataSource"].update(type="http"),
        lambda widget: widget.update(script="alert(1)"),
        lambda widget: widget.update(dataSource={"type": "module-rpc"}),
    ],
    ids=[
        "missing-title",
        "missing-size",
        "unknown-size",
        "unknown-view-type",
        "overlong-title",
        "missing-value-path",
        "expression-value-path",
        "unknown-data-source",
        "unknown-widget-field",
        "missing-method",
    ],
)
def test_invalid_widgets_are_rejected(mutate) -> None:
    widget = copy.deepcopy(WIDGET)
    mutate(widget)
    with pytest.raises(ModuleError) as info:
        parse_manifest(_widget_manifest(widget))
    assert info.value.code == "INVALID_INPUT"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda page: page["layout"].append({"component": "iframe", "src": "ui/x.html"}),
        lambda page: page["layout"][1].pop("columns"),
        lambda page: page["layout"][1].update(script="alert(1)"),
        lambda page: page.update(title=""),
        lambda page: page.pop("layout"),
        _bad_form_field_type,
    ],
    ids=[
        "script-block",
        "table-without-columns",
        "block-extra-field",
        "empty-title",
        "missing-layout",
        "unknown-form-field-type",
    ],
)
def test_invalid_pages_are_rejected(mutate) -> None:
    page = copy.deepcopy(PAGE)
    mutate(page)
    with pytest.raises(ModuleError) as info:
        parse_manifest(_page_manifest(page))
    assert info.value.code == "INVALID_INPUT"


def test_tool_definition_passes() -> None:
    manifest = parse_manifest(_manifest(contributes={"tools": [TOOL]}))
    tool = manifest.contributes["tools"][0]
    assert tool["inputSchema"]["type"] == "object"


def test_tool_parameters_alias_passes() -> None:
    tool = {key: value for key, value in TOOL.items() if key != "inputSchema"}
    tool["parameters"] = {"type": "object", "properties": {"days": {"type": "integer"}}}
    manifest = parse_manifest(_manifest(contributes={"tools": [tool]}))
    assert manifest.contributes["tools"][0]["parameters"]["type"] == "object"


@pytest.mark.parametrize(
    "tool",
    [
        {**TOOL, "parameters": {"type": "object"}},
        {**TOOL, "permissions": ["totally:unknown"]},
        {**TOOL, "longRunning": "yes"},
        {**TOOL, "description": ""},
        {**TOOL, "script": "run()"},
    ],
    ids=[
        "input-schema-and-parameters",
        "unknown-tool-permission",
        "non-boolean-long-running",
        "empty-description",
        "unknown-tool-field",
    ],
)
def test_invalid_tools_are_rejected(tool: dict) -> None:
    with pytest.raises(ModuleError) as info:
        parse_manifest(_manifest(contributes={"tools": [tool]}))
    assert info.value.code == "INVALID_INPUT"


def test_legacy_manifests_still_pass() -> None:
    paths = [
        ROOT / "modules" / "demo.echo" / "module.json",
        ROOT / "modules" / "official" / "cardia" / "module.json",
        *sorted((ROOT / "schemas" / "examples").glob("*.module.json")),
    ]
    for path in paths:
        manifest = load_manifest_file(path)
        assert manifest.id
    assert len(paths) >= 5
