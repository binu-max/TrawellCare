import re

from tc_common import ValidationFailed

_TOKEN = re.compile(r"\{(\w+)\}")


def render(template: str, variables: dict) -> str:
    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in variables:
            raise ValidationFailed(f"Missing template variable {key}")
        return str(variables[key])

    return _TOKEN.sub(replace, template)
