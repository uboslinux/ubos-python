#!/usr/bin/python
#
# Setup the package.
#
# Copyright (C) 2014 and later, Indie Computing Corp. All rights reserved. License: see package.
#

from pathlib import Path
from setuptools import setup
import ubos.utils

setup(name='ubos-utils',
      version=Path('../PKGVER').read_text().strip(),
      packages=[
          'ubos'
      ],
      zip_safe=True)
