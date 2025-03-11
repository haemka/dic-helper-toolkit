from setuptools import setup, find_packages


setup(
    name='dic-helper-toolkit',
    version='0.6.0',
    packages=find_packages(),
    install_requires=[
        'requests',
        'requests-oauthlib',
        'oauthlib',
        'fhir.resources'
    ]
)
