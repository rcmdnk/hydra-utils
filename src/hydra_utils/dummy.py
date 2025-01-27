from __future__ import annotations

from typing import Any

from .utils import hydra_wrapper


@hydra_wrapper(
    app_name='dummy',
    app_version='0.1.0',
    app_file=__file__,
    version_base='1.2',
)
def main(conf_dict: dict[Any, Any]) -> None:
    print(conf_dict)  # noqa: T201
