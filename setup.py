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
    packages=find_packages(),
    py_modules=["vapor", "doctor", "resource_plan", "openai_server", "config"],
    include_package_data=True,
    package_data={
        "": ["c/vapor_engine", "web/dist/*", "web/dist/assets/*"]
    },
)
