import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from omegaconf import DictConfig, OmegaConf

from hydra_utils.utils import read_conf


@pytest.fixture
def tmp_obj(tmp_path: pytest.fixture) -> tuple:
    test1 = tmp_path / 'test1.yml'
    test1.write_text(
        """---
a: 1
b: 2
c:
 - 1
 - 2
 - 3
d:
  d1: 1
  d2: 2
""",
    )
    test2 = tmp_path / 'test2.yml'
    test2.write_text(
        f"""---
a: 2
include:
  - {test1}
b: 3
""",
    )

    test3 = tmp_path / 'test3.yml'
    test3.write_text(
        f"""---
a: 3
include:
  - {test2}
""",
    )

    test4 = tmp_path / 'test4.yml'
    test4.write_text(
        """---
d:
  d2: 3
  d3: 3
""",
    )

    test5 = tmp_path / 'test5.yml'
    test5.write_text(
        f"""---
include:
  - {test3}
  - {test4}
""",
    )
    return (
        tmp_path,
        (test1, test5),
        (
            {
                'a': 1,
                'b': 2,
                'c': [1, 2, 3],
                'd': {'d1': 1, 'd2': 2},
            },
            {
                'a': 1,
                'b': 3,
                'c': [1, 2, 3],
                'd': {'d1': 1, 'd2': 3, 'd3': 3},
            },
        ),
    )


def test_read_conf(tmp_obj: pytest.fixture) -> None:
    test_files = tmp_obj[1]
    test_results = tmp_obj[2]
    conf = read_conf(str(test_files[0]))
    assert isinstance(conf, DictConfig)
    assert OmegaConf.to_container(conf) == test_results[0]

    conf = read_conf(str(test_files[1]))
    assert isinstance(conf, DictConfig)
    assert OmegaConf.to_container(conf) == test_results[1]


@pytest.mark.parametrize(
    ('conf_prefix', 'conf_file', 'result_file'),
    [
        ('conf_file=', 0, 0),
        ('+conf_file=', 0, 0),
        ('', 0, 0),
        ('conf_file=', 1, 1),
    ],
)
def test_log_conf(
    tmp_obj: pytest.fixture,
    monkeypatch: pytest.fixture,
    conf_prefix,
    conf_file,
    result_file,
) -> None:
    tmpdir = tmp_obj[0]
    test_files = tmp_obj[1]
    test_results = tmp_obj[2]
    argv = [
        'my_app',
        f'{conf_prefix}{test_files[conf_file]}',
        f'hydra.run.dir={Path(tmpdir) / "log"}',
    ]
    with monkeypatch.context() as m:
        m.setattr('sys.argv', argv)
        if 'main' in sys.modules:
            del sys.modules['main']
        from hydra_utils.dummy import main

        main()
        with Path(
            Path(tmpdir) / 'log' / '.hydra' / 'user_conf.yaml'
        ).open() as f:
            conf = yaml.safe_load(f)
        assert conf == test_results[result_file]


def test_log_conf_args(
    tmp_obj: pytest.fixture, monkeypatch: pytest.fixture
) -> None:
    tmpdir = tmp_obj[0]
    test_files = tmp_obj[1]
    test_results = tmp_obj[2]
    argv = [
        'my_app',
        f'conf_file={test_files[0]}',
        f'hydra.run.dir={Path(tmpdir) / "log2"}',
        '+b=9',
        '+d.d2=3',
        '+d.d3=4',
        '+e=5',
    ]
    with monkeypatch.context() as m:
        m.setattr('sys.argv', argv)
        if 'main' in sys.modules:
            del sys.modules['main']
        from hydra_utils.dummy import main

        main()
        with Path(
            Path(tmpdir) / 'log2' / '.hydra' / 'user_conf_orig.yaml'
        ).open() as f:
            conf = yaml.safe_load(f)
        assert conf == test_results[0]
        with Path(
            Path(tmpdir) / 'log2' / '.hydra' / 'user_conf.yaml'
        ).open() as f:
            conf = yaml.safe_load(f)
        result = deepcopy(test_results[0])
        result['b'] = 9
        result['d']['d2'] = 3
        result['d']['d3'] = 4
        result['e'] = 5
        assert conf == result
