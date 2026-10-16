"""Dependency-free validator for the JSON Schema subset used by this skill.

Unknown validation keywords fail closed. This is deliberately not a general
JSON Schema implementation: schemas must stay within this explicit subset.
"""
import json
from pathlib import Path
import re

KEYWORDS = {'$schema', '$id', 'title', 'description', 'type', 'required', 'properties',
            'additionalProperties', 'items', 'minItems', 'maxItems', 'uniqueItems',
            'minLength', 'minProperties', 'pattern', 'enum', 'const', 'anyOf'}


def validate(value, schema, path='$'):
    errors = []
    unsupported = set(schema) - KEYWORDS
    if unsupported:
        return [f'{path}: unsupported schema keywords {sorted(unsupported)}']
    if 'anyOf' in schema and not any(not validate(value, branch, path) for branch in schema['anyOf']):
        errors.append(f'{path}: does not satisfy any allowed shape')
    types = schema.get('type', [])
    if isinstance(types, str):
        types = [types]
    matches = {'object': isinstance(value, dict), 'array': isinstance(value, list),
               'string': isinstance(value, str), 'null': value is None,
               'boolean': isinstance(value, bool),
               'integer': isinstance(value, int) and not isinstance(value, bool),
               'number': isinstance(value, (int, float)) and not isinstance(value, bool)}
    if types and not any(matches.get(t, False) for t in types):
        return [f'{path}: expected {types}']
    if 'const' in schema and (value != schema['const'] or type(value) is not type(schema['const'])):
        errors.append(f'{path}: wrong constant')
    if 'enum' in schema and value not in schema['enum']:
        errors.append(f'{path}: invalid enum value')
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                errors.append(f'{path}.{key}: required')
        if len(value) < schema.get('minProperties', 0):
            errors.append(f'{path}: too few properties')
        for key, item in value.items():
            child = schema.get('properties', {}).get(key)
            if child is not None:
                errors.extend(validate(item, child, f'{path}.{key}'))
            elif schema.get('additionalProperties') is False:
                errors.append(f'{path}.{key}: unexpected property')
            elif isinstance(schema.get('additionalProperties'), dict):
                errors.extend(validate(item, schema['additionalProperties'], f'{path}.{key}'))
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')):
            errors.append(f'{path}: invalid array length')
        if schema.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            errors.append(f'{path}: duplicate items')
        for i, item in enumerate(value):
            errors.extend(validate(item, schema.get('items', {}), f'{path}[{i}]'))
    if isinstance(value, str):
        if len(value.strip()) < schema.get('minLength', 0):
            errors.append(f'{path}: empty or too short')
        if 'pattern' in schema and re.search(schema['pattern'], value) is None:
            errors.append(f'{path}: invalid pattern')
    return errors


def validate_file(value, filename):
    schema = json.loads((Path(__file__).resolve().parents[1] / 'references/schemas' / filename).read_text(encoding='utf-8'))
    def check(node, path='$schema'):
        errors = []
        if set(node) - KEYWORDS:
            errors.append(f'{path}: unsupported schema keywords {sorted(set(node) - KEYWORDS)}')
        for name, child in node.get('properties', {}).items():
            errors.extend(check(child, path + '.' + name))
        for name in ('items', 'additionalProperties'):
            if isinstance(node.get(name), dict):
                errors.extend(check(node[name], path + '.' + name))
        for index, child in enumerate(node.get('anyOf', [])):
            errors.extend(check(child, f'{path}.anyOf[{index}]'))
        return errors
    unsupported = check(schema)
    return unsupported or validate(value, schema)
