#!/usr/bin/env python3

from setuptools import setup

setup(name="kyrian",
      version="1.0",
      description="Frontend for duplicity",
      long_description="",
      long_description_content_type="text/plain",
      author="Simeon Scheib",
      author_email="",
      maintainer="Simeon Scheib",
      maintainer_email="",
      python_requires="!=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, <4",
      include_package_data=True,
      packages=[
        "kyrian"
        ],
      package_dir={
        "kyrian": "src"
        },
      scripts=[
        "bin/kyrian",
        ],
      install_requires=[
        "duplicity",
        "PyQt6",
        "pyyaml",
        "qt-material"
        ],
      )
