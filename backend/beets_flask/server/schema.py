from collections.abc import Iterable

from quart import Quart
from quart_schema import ExternalDocumentation, Info, QuartSchema
from quart_schema.openapi import (
    QUART_SCHEMA_HIDDEN_ATTRIBUTE,
    ExternalDocumentation,
    OpenAPIProvider,
)
from werkzeug.routing.rules import Rule


class BlueprintOnlyOpenAPIProvider(OpenAPIProvider):
    """Only show a specific blueprint in the openapi docs.

    This is a workaround for migrating our api to a proper
    speced version.
    """

    def __init__(self, app: Quart, extension: QuartSchema) -> None:
        super().__init__(app, extension)
        self._blueprint_prefix = "api_v1"

    def generate_rules(self) -> Iterable[Rule]:
        for rule in self._app.url_map.iter_rules():
            hidden = getattr(
                self._app.view_functions[rule.endpoint],
                QUART_SCHEMA_HIDDEN_ATTRIBUTE,
                False,
            )
            if (
                rule.endpoint.startswith(self._blueprint_prefix)
                and not hidden
                and not rule.websocket
            ):
                yield rule


quart_schema = QuartSchema(
    scalar_ui_path=None,
    redoc_ui_path=None,
    # swagger_ui_path=None,
    external_docs=ExternalDocumentation(
        url="https://beets-flask.readthedocs.io",
    ),
    conversion_preference="msgspec",
    info=Info(
        title="BeetsFlask API",
        version="0.1.0",
        description="A semi stable and publiclly usable api for your beets library and "
        "the beets flask import process.",
    ),
    openapi_provider_class=BlueprintOnlyOpenAPIProvider,
)
