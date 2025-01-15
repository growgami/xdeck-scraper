from setuptools import setup, find_packages

setup(
    name="ai_newsletter",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "playwright==1.41.2",
        "python-dotenv==1.0.0",
        "loguru==0.7.2",
        "pydantic==2.5.3"
    ],
) 