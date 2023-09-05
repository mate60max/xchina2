#!/usr/bin/env python3
# coding: utf-8

from __future__ import unicode_literals

import os
import io

try:
    import fcntl

    def _lock_file(f, exclusive):
        fcntl.flock(f, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)

    def _unlock_file(f):
        fcntl.flock(f, fcntl.LOCK_UN)
except ImportError:
    UNSUPPORTED_MSG = 'file locking is not supported on this platform'

    def _lock_file(f, exclusive):
        raise IOError(UNSUPPORTED_MSG)

    def _unlock_file(f):
        raise IOError(UNSUPPORTED_MSG)


class locked_file(object):
    def __init__(self, filename, mode, encoding=None):
        assert mode in ['r', 'a', 'w']
        self.f = io.open(filename, mode, encoding=encoding)
        self.mode = mode

    def __enter__(self):
        exclusive = self.mode != 'r'
        try:
            _lock_file(self.f, exclusive)
        except IOError:
            self.f.close()
            raise
        return self

    def __exit__(self, etype, value, traceback):
        try:
            _unlock_file(self.f)
        finally:
            self.f.close()

    def __iter__(self):
        return iter(self.f)

    def write(self, *args):
        return self.f.write(*args)

    def read(self, *args):
        return self.f.read(*args)

def read_plain_urls(path):
    if not os.path.exists(path):
        return []
    with locked_file(path, 'r', encoding='utf-8') as f:
        return f.read().splitlines()

def write_plain_urls(urls, file):
    with locked_file(file, 'w', encoding='utf-8') as f:
        # f.writelines(urls)
        for url in urls:
            f.write(f'{url}\n')