"""Setuptools configuration."""


from setuptools import find_packages, setup

setup(
    name="nutrition",
    packages=find_packages(exclude=["tests*"]),
    version="0.1",
)
