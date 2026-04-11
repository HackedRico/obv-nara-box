from setuptools import setup, find_packages

setup(
    name="nara",
    version="0.1.0",
    description="Autonomous AI-powered penetration testing CLI",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "anthropic>=0.40.0",
        "ollama>=0.4.0",
        "python-dotenv>=1.0.0",
        "rich>=13.0.0",
        "prompt_toolkit>=3.0.0",
        "requests>=2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "nara=nara.cli:main",
        ]
    },
)
