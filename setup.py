from setuptools import setup, find_packages


setup(
    name='dic-helper-toolkit',
    version='0.5.2',
    packages=find_packages(),
    install_requires=[
        'requests',
        'requests-oauthlib',
        'oauthlib',
        'fhir.resources'
    ]
)
