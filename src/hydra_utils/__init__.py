from .utils import hydra_wrapper, to_absolute_path

__all__ = ['__version__', 'hydra_wrapper', 'to_absolute_path']


def __getattr__(name: str) -> str:
    if name == '__version__':
        from .version import __version__

        return __version__
    msg = f'module {__name__} has no attribute {name}'
    raise AttributeError(msg)
