from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

import hydra

if TYPE_CHECKING:
    from omegaconf import DictConfig


HYDRA_USER_CONF_ORIG = '.hydra/user_conf_orig.yaml'
HYDRA_USER_CONF = '.hydra/user_conf.yaml'


def to_absolute_path(path: str) -> str:
    if not path:
        return path
    if ':' in str(path):  # s3://..., https://...
        return path

    return hydra.utils.to_absolute_path(path)


def fix_argv(argv: list[str]) -> list[str]:
    """Add conf_file=... to sys.argv if no conf_file=... is given and a positional argument is given."""
    conf_file = ''
    argv = argv.copy()
    for i in range(1, len(argv)):
        if '=' not in argv[i]:
            if Path(argv[i]).exists():
                conf_file = argv[i]
                argv.pop(i)
                break

        elif argv[i].startswith('conf_file='):
            argv[i] = f'+{argv[i]}'
            conf_file = ''
            break
        elif argv[i].startswith('+conf_file='):
            conf_file = ''
            break
    if conf_file:
        argv.append(f'+conf_file={conf_file}')
    return argv


def merge_conf(conf1: DictConfig, conf2: DictConfig) -> DictConfig:
    from omegaconf import DictConfig, OmegaConf

    return cast(DictConfig, OmegaConf.merge(conf1, conf2))


def read_conf(conf_path: str, base_conf_path: str = '') -> DictConfig:
    """Read configuration file.

    Parameters
    ----------
    conf_path : str
        Path to configuration file.
    base_conf_path : str
        If not empty, base_conf_path is the parent path of the conf_path when
        conf_path does not start with '/'.

    Returns
    -------
    DictConfig
        Configuration file.

    """
    if not conf_path.startswith('/'):
        if base_conf_path:
            conf_path = str(Path(base_conf_path).parent / Path(conf_path))
        conf_path = to_absolute_path(conf_path)

    from omegaconf import ListConfig, OmegaConf

    conf = OmegaConf.load(conf_path)
    if isinstance(conf, ListConfig):
        msg = f'{conf_path} is not a dictionary format.'
        raise TypeError(msg)
    conf_final = OmegaConf.create({})
    conf_pre = OmegaConf.create({})
    for key in conf:
        if key == 'include':
            conf_final = merge_conf(conf_final, conf_pre)
            conf_pre = OmegaConf.create({})
            for include_path in conf[key]:
                conf_final = merge_conf(
                    conf_final,
                    read_conf(include_path, conf_path),
                )
        else:
            conf_pre[key] = conf[key]
    return merge_conf(conf_final, conf_pre)


def main_opt(
    config_path: str, config_name: str, version_base: str
) -> dict[str, str]:
    opt: dict[str, str] = {}
    if config_path:
        opt['config_path'] = config_path
    if config_name:
        opt['config_name'] = config_name
    if version_base:
        opt['version_base'] = version_base
    return opt


def update_conf(conf: DictConfig) -> dict[Any, Any]:
    from omegaconf import OmegaConf

    if 'conf_file' in conf:
        # Override configurations by user_config (conf).
        # Command line options will overwrite these user_config parameters.
        # (No default conf parameters other than `conf`.)
        output_dir = (
            hydra.core.hydra_config.HydraConfig.get().runtime.output_dir
        )
        user_conf = read_conf(conf.conf_file)
        OmegaConf.save(user_conf, f'{output_dir}/{HYDRA_USER_CONF_ORIG}')
        OmegaConf.set_struct(conf, False)
        del conf['conf_file']
        conf_merge = merge_conf(user_conf, conf)
        OmegaConf.save(conf_merge, f'{output_dir}/{HYDRA_USER_CONF}')
        conf_dict = OmegaConf.to_container(conf_merge, resolve=True)
    else:
        conf_dict = OmegaConf.to_container(conf, resolve=True)

    if not isinstance(conf_dict, dict):
        msg = 'Config is not a dictionary.'
        raise TypeError(msg)

    conf_dict = get_conf_dict(conf_dict)

    return conf_dict


def check_git(file: str, log: logging.Logger) -> None:
    try:
        from git import Repo
        from git.exc import InvalidGitRepositoryError, NoSuchPathError

        try:
            repo = Repo(Path(file).parent.parent.parent)
            log.info('Commit hash: %s', repo.head.commit.hexsha)
            t = repo.head.commit.tree
            log.info(repo.git.diff(t))
        except NoSuchPathError:
            log.info("This is not a git repository's one.")
        except InvalidGitRepositoryError:
            log.info("This is not a git repository's one.")
        log.info('Running in %s.', Path.cwd())
    except ImportError:
        log.info('git is not installed.')


def cpu_count(n_jobs: int | None) -> int:
    """Return number of cpu cores to used.

    Parameters
    ----------
    n_jobs : int | None
        Number of cpu cores to be used. If None, use all physical cores. If -1,
        use all logical cores. If 0 or 1, run in serial. If negative, use all
        logical cores + 1 + n_jobs.

    """
    if n_jobs is None:
        from joblib import cpu_count

        return cpu_count(only_physical_cores=True)
    if n_jobs < 0:
        from os import cpu_count

        return cpu_count() + 1 + n_jobs
    if n_jobs == 0:
        return 1
    return n_jobs


def fix_n_jobs(conf_dict: dict[Any, Any]) -> None:
    conf_dict['n_jobs'] = cpu_count(conf_dict.get('n_jobs', -1))


def fix_conf(conf_dict: dict[Any, Any]) -> None:
    fix_n_jobs(conf_dict)


def get_conf_dict(conf_dict: dict[Any, Any] | str) -> dict[Any, Any]:
    if isinstance(conf_dict, str):
        from omegaconf import OmegaConf

        conf = read_conf(conf_dict)
        conf_dict = cast(
            dict[str, Any],
            OmegaConf.to_container(conf, resolve=True),
        )
    fix_conf(conf_dict)
    return conf_dict


def set_log(log_format: str, log_level: str) -> logging.Logger:
    log = logging.getLogger(__name__)
    if log_format:
        formatter = logging.Formatter(log_format)
        for h in log.root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.setFormatter(formatter)
    if log_level:
        log.root.setLevel(log_level)
    return log


def starting_log(
    log: logging.Logger, app_name: str, app_version: str, app_file: str
) -> None:
    output = f'Starting {app_name}'
    if app_version:
        output += f' version: {app_version}'
    log.info(output)
    log.info('Python version: %s', sys.version)
    if app_file:
        check_git(app_file, log)


def ending_log(log: logging.Logger, cwd: Path) -> None:
    log.info('Finished. Output directory: %s', cwd)


def run_with_check_profile(
    run: Callable[[dict[Any, Any]], None],
    conf_dict: dict[Any, Any],
    log: logging.Logger,
) -> None:
    import cProfile
    import io
    import pstats

    conf_dict['n_jobs'] = 1
    profile = 'profile'
    cProfile.runctx('run(conf_dict)', globals(), locals(), profile)

    s = io.StringIO()
    p = pstats.Stats(profile, stream=s)
    p.strip_dirs()
    p.sort_stats(pstats.SortKey.CUMULATIVE).print_stats()
    log.info(s.getvalue())


def hydra_wrapper(  # noqa: C901
    app_name: str = '',
    app_version: str = '',
    app_file: str = '',
    config_path: str = '',
    config_name: str = '',
    version_base: str = '',
    verbose: int = 1,
) -> Callable[[Callable[[dict[Any, Any]], None]], Callable[[], None]]:
    def _wrapper(
        run: Callable[[dict[Any, Any]], None],
    ) -> Callable[[], None]:
        sys.argv = fix_argv(sys.argv)

        caller = inspect.stack()[1].filename
        if config_path:
            _config_path = str(Path(caller).parent / Path(config_path))
        else:
            _config_path = ''

        if app_file:
            _app_file = app_file
        else:
            _app_file = caller

        @hydra.main(**(main_opt(_config_path, config_name, version_base)))
        def hydra_main(conf: DictConfig) -> None:
            conf_dict = update_conf(conf)
            _app_name = (
                app_name
                if app_name
                else conf_dict.get('app_name', sys.argv[0])
            )
            _app_version = (
                app_version
                if app_version
                else conf_dict.get('app_version', '')
            )

            log = set_log(
                conf_dict.get('log_format', ''),
                conf_dict.get('log_level', ''),
            )
            if verbose > 0:
                starting_log(log, _app_name, _app_version, _app_file)
            exit_code = 0
            try:
                if conf_dict.get('check_profile', False):
                    run_with_check_profile(run, conf_dict, log)
                else:
                    run(conf_dict)
            except Exception as e:
                exit_code = 1
                for arg in e.args:
                    log.exception(arg)
            if verbose > 0:
                ending_log(log, Path.cwd())
            if exit_code:
                sys.exit(exit_code)

        return hydra_main

    return _wrapper
