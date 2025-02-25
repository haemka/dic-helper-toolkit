from setuptools import setup, find_packages


setup(
    name='dic-helper-toolkit',
    version='0.5.3',
    packages=find_packages(),
    install_requires=[
        'requests',
        'requests-oauthlib',
        'oauthlib',
        'fhir.resources'
    ]
)
