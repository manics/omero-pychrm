#!/usr/bin/env python

"""
setup.py file for OmeroWndcharm
"""

from setuptools import setup

import version

setup(
    name='OmeroWndcharm',
    version=version.get_git_version(),
    author='Simon Li',
    author_email='spli@dundee.ac.uk',
    packages=['OmeroWndcharm'],
    url='http://www.openmicroscopy.org/',
    license='LICENSE.txt',
    description='Scripts for using WND-CHARM in OMERO',
    long_description=open('README.md').read(),
    install_requires=[
        'wndcharm>=0.1.0',
        ],
    #dependency_links=['git+https://github.com/wnd-charm/wnd-charm.git'],
)
