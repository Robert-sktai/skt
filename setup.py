import setuptools


def load_long_description():
    with open("README.md", "r") as f:
        long_description = f.read()
    return long_description


# Start dependencies group
air = [
    "bayesian-optimization==1.1.0",
    "catboost<1.0.0",
    "plotnine<1.0.0",
    "shap==0.35.0",
    "gensim==3.8.1",
    "torch==1.4.0",
    "torchvision==0.5.0",
    "seaborn==0.10.0",
    "scikit-learn==0.22.2.post1",
    "scipy==1.4.1",
    "lifelines==0.24.2",
    "xgboost==1.0.2",
    "lightgbm==2.3.1",
    "implicit==0.4.2",
    "tqdm==4.43.0",
    "matplotlib==3.2.1",
    "mushroom_rl==1.4.0",
    "pytorch-widedeep==0.3.7",
    "RL-for-reco==1.0.13",
    "LightGBMwithBayesOpt==1.0.2",
]

setuptools.setup(
    name="skt",
    version="0.2.17",
    author="SKT",
    author_email="all@sktai.io",
    description="SKT package",
    long_description=load_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/sktaiflow/skt",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=[
        "thrift-sasl==0.3.0",
        "hvac>=0.9.6",
        "pyhive[hive]==0.6.2",
        "pyarrow<1.0.0",
        "pandas==1.1.0",
        "slackclient>=2.5.0",
        "google-cloud-bigquery==1.26.1",
        "httplib2>=0.18.0",
        "click",
        "PyGithub",
        "pycryptodome",
        "tabulate>=0.8.7",
        "pandas_gbq",
        "google-cloud-bigquery-storage",
        "grpcio<2.0dev",
        "sqlalchemy>=1.3.0",
    ],
    entry_points={"console_scripts": ["nes = skt.nes:nes_cli"]},
    extras_require={"air": air},
)
