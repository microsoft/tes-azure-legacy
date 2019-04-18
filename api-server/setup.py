#!/usr/bin/env python

from setuptools import find_packages
from setuptools import setup


def find_subpackages(package):
    packages = [package]
    for subpackage in find_packages(package):
        packages.append("{0}.{1}".format(package, subpackage))
    return packages


setup(name="tesazure",
      version="0.1",
      description="A GA4GH Task Execution service (TES) API Server for Azure Compute",
      url="",
      author="Microsoft Commercial Software Engineering (CSE) - Health Industry team",
      packages=find_subpackages("tesazure"),
      license='MIT')
