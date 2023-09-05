#!/usr/bin/env python3
# coding: utf-8

from __future__ import unicode_literals

__license__ = 'Public Domain'

import sys
from . import xchina2

def main(argv=None):
    try:
        xchina2.real_main(argv)
    except KeyboardInterrupt:
        sys.exit('\nERROR: Interrupted by user')


__all__ = ['main']
