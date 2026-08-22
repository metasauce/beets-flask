import inspect
import re
from collections.abc import Iterable
from typing import Any

from quart import Quart
from quart_schema import ExternalDocumentation, Info, QuartSchema, Tag
from quart_schema.openapi import (
    QUART_SCHEMA_HIDDEN_ATTRIBUTE,
    ExternalDocumentation,
    OpenAPIProvider,
)
from quart_schema.typing import Model
from werkzeug.routing.converters import BaseConverter
from werkzeug.routing.rules import Rule


def _add_enum_types(node: Any) -> None:
    """Recursively add an explicit ``type: string`` to enum-only schemas.

    msgspec emits a bare ``enum`` (without ``type``) for ``Literal``
    types, which swagger renders as "any" (e.g. the ``type`` field of a
    resource). Adding the explicit string type makes the docs show the
    actual value type.
    """
    if isinstance(node, dict):
        if "enum" in node and "type" not in node:
            node["type"] = "string"
        for value in node.values():
            _add_enum_types(value)
    elif isinstance(node, list):
        for item in node:
            _add_enum_types(item)


class BlueprintOnlyOpenAPIProvider(OpenAPIProvider):
    """Only show a specific blueprint in the openapi docs.

    This is a workaround for migrating our api to a proper
    speced version.
    """

    # Preferred order of HTTP methods within a path in the docs.
    _METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}

    # Descriptions for the path parameters of our endpoints.
    _PATH_PARAM_DESCRIPTIONS = {
        "album_id": "The id of the album in the beets library",
        "item_id": "The id of the item in the beets library",
    }

    def __init__(self, app: Quart, extension: QuartSchema) -> None:
        super().__init__(app, extension)
        self._blueprint_prefix = "api_v1"

    def generate_rules(self) -> Iterable[Rule]:
        """Yield the rules ordered by path, then by HTTP method.

        Paths with path parameters (single resource, e.g. ``/albums/{id}``)
        come before the collection paths (bulk, e.g. ``/albums/``), so the
        single and bulk GET operations are grouped together at the top of
        each section. Methods are ordered GET, PATCH, DELETE, ...
        """
        rules = [
            rule
            for rule in self._app.url_map.iter_rules()
            if (
                rule.endpoint.startswith(self._blueprint_prefix)
                and not getattr(
                    self._app.view_functions[rule.endpoint],
                    QUART_SCHEMA_HIDDEN_ATTRIBUTE,
                    False,
                )
                and not rule.websocket
            )
        ]
        return sorted(
            rules,
            key=lambda rule: (
                # Sort single-resource paths before collection paths.
                re.sub(r"/<[^>]+>", "\x00", rule.rule),
                min(self._METHOD_ORDER.get(method, 99) for method in rule.methods),
            ),
        )

    def generate_methods(self, rule: Rule) -> Iterable[str]:
        """Yield the rule's methods ordered by :attr:`_METHOD_ORDER`."""
        methods = [
            method
            for method in (rule.methods or ())
            if method != "HEAD"
            and not (
                # Quart rules carry this attribute; werkzeug's typing
                # does not know about it.
                method == "OPTIONS"
                and getattr(rule, "provide_automatic_options", False)
            )
        ]
        return sorted(methods, key=lambda method: self._METHOD_ORDER.get(method, 99))

    def build_path_parameter(
        self, name: str, converter: BaseConverter
    ) -> dict[str, Any]:
        """Add descriptions to the known path parameters."""
        parameter = super().build_path_parameter(name, converter)
        if name in self._PATH_PARAM_DESCRIPTIONS:
            parameter["description"] = self._PATH_PARAM_DESCRIPTIONS[name]
        return parameter

    def build_response_object(
        self, model: type[Model], headers_model: type[Model] | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build a response object, splitting the model docstring.

        The first line of the docstring becomes the response description,
        which keeps the swagger response rows compact. The remaining lines
        (the docstring description) are shown in the response schema
        instead, where multiline text renders fine.
        """
        response_object, components = super().build_response_object(
            model, headers_model
        )
        docstring = inspect.getdoc(model)
        if docstring:
            summary, *description = docstring.splitlines()
            response_object["description"] = summary
            description = "\n".join(description).strip()
            if description:
                schema = (
                    response_object.get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
                if schema is not None:
                    schema["description"] = description
        # msgspec keeps the raw indentation of the class docstrings in the
        # component schemas - clean it up so it renders nicely.
        for definition in components.values():
            if "description" in definition:
                definition["description"] = inspect.cleandoc(definition["description"])
        return response_object, components

    def schema(self) -> dict[str, Any]:
        """Build the openapi document, adding explicit types to enum schemas.

        msgspec emits a bare ``enum`` (without ``type``) for ``Literal``
        types, which swagger renders as "any" (e.g. the ``type`` field of
        a resource). Add an explicit string type everywhere in the
        document, so the docs render the actual value type.
        """
        document = super().schema()
        _add_enum_types(document)
        return document


quart_schema = QuartSchema(
    scalar_ui_path=None,
    redoc_ui_path=None,
    # swagger_ui_path=None,
    external_docs=ExternalDocumentation(
        url="https://beets-flask.readthedocs.io",
        description="Check out the docs for more information about BeetsFlask.",
    ),
    tags=[
        Tag(
            name="items",
            description="Retrieve and modify items in your beets library.",
        ),
        Tag(
            name="albums",
            description="Retrieve and modify albums in your beets library.",
        ),
    ],
    conversion_preference="msgspec",
    info=Info(
        title="BeetsFlask API",
        version="0.1.0",
        description=(
            "The BeetsFlask API gives you programmatic access to your beets "
            "music library. Retrieve and manage albums and items, and build "
            "your own scripts, automations, and applications on top of a "
            "consistent, machine-readable format.\n\n"
            "We follow the JSON:API style in our responses. The structure is "
            "the same across all endpoints and explained below, so you can "
            "use the API without any prior knowledge of JSON:API. "
            "All responses share the same structure:\n\n"
            "- ``data``: the requested resource(s), e.g. an album or an item\n"
            "- ``attributes``: the fields of a resource, e.g. its title\n"
            "- ``relationships``: related resources, referenced by ``type`` and ``id``\n"
            "- ``included``: the full related resources, when requested via ``include``\n"
            "- ``links``: pagination links, e.g. the URL of the next page\n"
            "- ``meta``: additional information, e.g. the total number of results\n"
        ),
    ),
    openapi_provider_class=BlueprintOnlyOpenAPIProvider,
)
