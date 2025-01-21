from setuptools import setup, find_packages


setup(
    name='dic-helper-toolkit',
    version='0.3.0',
    packages=find_packages(),
    install_requires=[
        'requests',
        'requests-oauthlib',
        'fhir.resources'
    ]
)
