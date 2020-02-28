import setuptools

# Start dependencies group
air = [
    'bayesian-optimization>=1.1.0',
    'shap>=0.34.0',
    'gensim>=3.8.1',
    'torch>=1.4.0',
    'torchvision>=0.5.0',
    'seaborn>=0.10.0',
    'scikit-learn>=0.22.1',
    'lifelines>=0.24.0',
    'xgboost>=1.0.1',
    'lightgbm>=2.3.1',
    'implicit>=0.4.2',
    'tqdm>=4.43.0',
    'matplotlib>=3.1.3',
]

setuptools.setup(
    name="skt",
    version="0.1.11",
    author="SKT",
    author_email="all@sktai.io",
    description="SKT package",
    url="https://github.com/sktaiflow/skt",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        'hvac>=0.9.6',
        'pyhive[hive]',
        'pyarrow>=0.16.0',
        'pandas>=1.0.1',
        'slackclient>=2.5.0',
    ],
    extras_require={
        'air': air,
    }
)
