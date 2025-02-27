from setuptools import setup, find_packages

setup(
    name='t2-cicd',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'requests',
        'fastapi',
        'uvicorn',
        'pydantic',
        'docker',
        'psycopg2-binary',
        'annotated-types==0.7.0',
        'anyio==4.6.2',
        'certifi==2024.8.30',
        'charset-normalizer==3.4.0',
        'click==8.1.7',
        'docker==7.1.0',
        'exceptiongroup==1.2.2',
        'fastapi==0.115.4',
        'gitdb==4.0.11',
        'GitPython==3.1.43',
        'httpx==0.25.1',
        'h11==0.14.0',
        'idna==3.10',
        'iniconfig==2.0.0',
        'packaging==24.1',
        'pathspec==0.12.1',
        'pluggy==1.5.0',
        'psycopg==3.2.3',
        'psycopg2-binary==2.9.9',
        'pydantic==2.9.2',
        'pydantic_core==2.23.4',
        'pytest==8.3.3',
        'python-dotenv==1.0.1',
        'PyYAML==6.0.2',
        'requests==2.32.3',
        'ruamel.yaml==0.18.6',
        'ruamel.yaml.clib==0.2.8',
        'smmap==5.0.1',
        'sniffio==1.3.1',
        'starlette==0.41.2',
        'tomli==2.0.2',
        'typing_extensions==4.12.2',
        'urllib3==2.2.3',
        'uvicorn==0.32.0',
        'pytest-mock==3.14.0'
    ],
    entry_points={
        'console_scripts': [
            't2-cicd=cli.main:main',
        ],
    },
    description="A CI/CD tool for running pipelines locally",
)
