from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

import hydra

if TYPE_CHECKING:
    from omegaconf import DictConfig


HYDRA_USER_CONF_ORIG = Path('./.hydra/user_conf_orig.yaml')
HYDRA_USER_CONF = Path('./.hydra/user_conf.yaml')


def to_absolute_path(path: str) -> str:
    if not path:
        return path
    if ':' in str(path):  # s3://..., https://...
        return path

    return hydra.utils.to_absolute_path(path)


def fix_argv() -> None:
    """Add conf=... to sys.argv if no conf=... is given and a positional argument is given."""
    conf_cand: list[str] = []
    for v in sys.argv[1:]:
        if '=' not in v:
            conf_cand.append(v)
        elif v.startswith('conf='):
            conf_cand = []
            break
    if conf_cand:
        for c in conf_cand:
            if Path(c).exists():
                sys.argv.remove(c)
                sys.argv.append(f'conf={c}')
                break


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


def update_conf(conf: DictConfig) -> dict[Any, Any]:
    from omegaconf import OmegaConf

    if conf.conf:
        # Override configurations by user_config (conf).
        # Command line options will overwrite these user_config parameters.
        # (No default conf parameters other than `conf`.)
        user_conf = read_conf(conf.conf)
        OmegaConf.save(user_conf, HYDRA_USER_CONF_ORIG)
        OmegaConf.set_struct(conf, False)
        del conf['conf']
        conf_merge = merge_conf(user_conf, conf)
        OmegaConf.save(conf_merge, HYDRA_USER_CONF)
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


def hydra_wrapper(
    app_name: str = '',
    app_version: str = '',
    app_file: str = '',
    config_path: str = 'conf',
    config_name: str = 'config',
    version_base: str = '1.2',
) -> Callable[
    [Callable[[dict[Any, Any]], None]], Callable[[dict[Any, Any]], None]
]:
    def _wrapper(
        run: Callable[[dict[Any, Any]], None],
    ) -> Callable[[dict[Any, Any]], None]:
        fix_argv()

        @hydra.main(
            config_path=config_path,
            config_name=config_name,
            version_base=version_base,
        )
        def hydra_main(conf: DictConfig) -> None:
            conf_dict = update_conf(conf)
            _app_name = app_name if app_name else conf_dict.get('app_name', '')
            _app_version = (
                app_version
                if app_version
                else conf_dict.get('app_version', '')
            )
            if not _app_name:
                _app_name = 'App'

            log = set_log(
                conf_dict.get('log_format', ''),
                conf_dict.get('log_level', ''),
            )
            if _app_version:
                if not _app_name:
                    _app_name = 'App'
                log.info(f'{_app_name} version: {_app_version}')
            log.info('Python version: %s', sys.version)
            if app_file:
                check_git(app_file, log)

            exit_code = 0
            try:
                if conf_dict.get('check_profile', False):
                    run_with_check_profile(run, conf_dict, log)
                else:
                    run(conf_dict)
            except Exception as e:
                exit_code = e.args[0] if e.args else 1
                log.exception(e.args[1] if e.args else '')
            log.info('Finished. Output directory: %s', Path.cwd())
            if exit_code:
                sys.exit(exit_code)

        return hydra_main

    return _wrapper
