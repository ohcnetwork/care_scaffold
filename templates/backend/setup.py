#!/usr/bin/env python

"""The setup script."""

from setuptools import find_packages, setup

with open("README.md") as readme_file:
    readme = readme_file.read()

requirements = [
    "celery",
    "django",
    "djangorestframework",
    "django-environ",
    "django-filter",
]

setup(
    author="Open Healthcare Network",
    author_email="info@ohc.network",
    python_requires=">=3.13",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.13",
    ],
    description="__PLUGIN_DESCRIPTION__",
    install_requires=requirements,
    license="MIT license",
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords="__PLUGIN_SNAKE__",
    name="__PLUGIN_SNAKE__",
    packages=find_packages(include=["__PLUGIN_SNAKE__", "__PLUGIN_SNAKE__.*"]),
    url="https://github.com/ohcnetwork/__PLUGIN_SNAKE__",
    version="0.1.0",
    zip_safe=False,
)
