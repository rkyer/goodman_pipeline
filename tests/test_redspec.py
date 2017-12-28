from __future__ import absolute_import


def test_get_args():
    from ..pipeline.spectroscopy.redspec import get_args
    import argparse
    arguments = ['--data-path', './',
                 '--proc-path', './',
                 '--search-pattern', 'test-pattern',
                 '--output-prefix', 'g',
                 '--extraction', 'simple']

    args = get_args(arguments)

    assert isinstance(args, argparse.Namespace)
    assert args.pattern == 'test-pattern'
    return args


if __name__ == '__main__':
    test_get_args()