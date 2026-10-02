"""Machine-readable contract catalog. Schema generation never loads plugin code."""
from .content import CONTENT_MODELS
from .plugin import Manifest
from .presets import PRESET_MODELS

AUTHOR_MODELS = {**CONTENT_MODELS, **PRESET_MODELS}
CONTENT_FORMATS = {kind: model.model_fields['format'].annotation.__args__[0] for kind, model in CONTENT_MODELS.items()}


def schema_for(kind):
    model = Manifest if kind == 'plugin' else AUTHOR_MODELS.get(kind)
    if model is None:
        raise ValueError('不存在的创作契约')
    schema = model.model_json_schema(by_alias=True)
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = f'urn:ember-tavern:{kind}:v1'
    return schema
