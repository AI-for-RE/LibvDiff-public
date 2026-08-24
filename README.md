# LibvDiff Artifact

LibvDiff is a precise and efficient open-source software (OSS) version identification tool. It is designed to identify OSS versions in a fine-grained level, even though no version strings are available in the target binary. Here is the artifact related to LibvDiff, including the code and the dataset.

This repository is a forked version of LibvDiff, with the intention of running and evaluating against datasets for the AI-For-RE analyzer. See the original repository for more information about LibvDiff itself.

## Running environment construction manually

Note this environment differs from the one from the original Libvdiff (our dependency versions are more recent).

1. Initial requirements

```shell
apt install wget bzip2 git
```

2. Install conda

3. Create a python environment and activate it

```shell
conda create --name libvdiff python=3.10
conda activate libvdiff
```

4. Install python packages

```shell
pip install pytorch torchvision torchaudio -c pytorch \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  -f https://data.pyg.org/whl/torch-2.8.0+cu129.html
pip install -r requirements.txt
```

## IDA Pro install

- IDA Pro 7.5+ on linux: 

  - Make sure the IDA Python switches to python3

  - Extra python packages are required to install for IDA Python: `PATH_TO_IDA_PYTHON -m pip install cptools==2.0.1 networkx==2.4"`
