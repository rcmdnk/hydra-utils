# hydra-utils

[![test](https://github.com/rcmdnk/hydra-utils/actions/workflows/test.yml/badge.svg)](https://github.com/rcmdnk/hydra-utils/actions/workflows/test.yml)
[![test coverage](https://img.shields.io/badge/coverage-check%20here-blue.svg)](https://github.com/rcmdnk/hydra-utils/tree/coverage)

Wrapper for ([hydra-core](https://pypi.org/project/hydra-core/) to add flexible configuration treatment.

## Requirement

- Python 3.13, 3.12, 3.11, 3.10

## Installation

```bash
pip install hydra-utils
```

## Usage

```python
@hydra_utils.hydra_wrapper(
    app_name='my_app',
    app_version='0.1.0',
    app_file=__file__,
    conf_path='conf',
    conf_name='config',
    version_base='1.2',
)
def main(conf: dict[Any, Any]) -> None: ...


if __name__ == '__main__':
    main()
```

- `app_name` and `app_version` are used to log information of current version.
  - It is useful if app_version is set to `__version__` of the app.
- `app_file` is used to check the file place's git status to log the git commit hash and diff from the last commit.
- The argument which the main function takes is `dict[Any, Any]` instead of `DictConfig`.
- Configuration file can be passed by the first argument or `conf_file=...` at the command line, which will be merged to the configuration file specified by conf_path and conf_name.
- Configuration file can have `include` keyword which has the list of configuration files to include.
  - Included files are merged to the main configuration file.
  - It is resolved at the place of `include`. If the main file has other configurations after the `include`, they will overwrite the included configurations.
- `n_jobs` is fixed to the number of CPUs.
  - It is used to set the number of jobs for parallel processing.
  - If `n_jobs` is set to 0 or 1, it is set to 1.
  - If `n_jobs` is set to -1, it is set to the number of logical cores.
  - If `n_jobs` is set to None, it is set to the number of physical cores.
  - If `n_jobs` is set to a negative number, it is set to the number of logical cores + 1 + n_jobs, i.e. -1 is the same as the number of logical cores.

It is recommended to define `hydra.job.name` in your default configuration file (`<conf_pth>/<conf_name>.yaml`):

```
hydra:
  job:
    name: my_custom_job_name
```

Otherwise the job name is `utils` as hydra detect the file where `hydra.main` is executed.

There is also wrapper function for `to_absolute_path`.

```python
from hydra_utils import to_absolute_path
```

- It returns empty string if the input is empty.
- It returns the input as is if the input includes `:` (e.g., `http://`, `s3://`, ...).

Based on [rcmdnk/python-template](https://github.com/rcmdnk/python-template), v0.1.2
