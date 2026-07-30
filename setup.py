from setuptools import setup, find_packages
import subprocess, os

# Custom build step to compile C engine binary
def build_c_engine():
    c_dir = os.path.join(os.path.dirname(__file__), "c")
    if os.path.exists(c_dir):
        subprocess.check_call(["make", "-C", c_dir])

build_c_engine()

setup(
    name="vapor-ram",
    version="1.0.0",
    description="Ultra-Low RAM SSD Streaming Engine for google/gemma-4-E4B-it (< 1.5 GB RAM)",
    long_description=open("README.md").read() if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="sudsarkar13",
    license="Apache-2.0",
    packages=find_packages(),
    py_modules=["doctor", "resource_plan", "openai_server", "config"],
    scripts=["vapor"],
    include_package_data=True,
    package_data={
        "": ["c/vapor_engine", "web/dist/*", "web/dist/assets/*"]
    },
    install_requires=[
        "numpy>=1.20.0"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux"
    ]
)
