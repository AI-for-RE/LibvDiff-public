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
pip install -r requirements.txt
pip install torch torchvision torchaudio \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  -f https://data.pyg.org/whl/torch-2.8.0+cu129.html
```

## Version identification

`libvdiff.py` identifies the version of the binaries of one library by comparing builds of it
against each other. The dataset layout and the feature generation it depends on are documented in
[data_process/README.md](data_process/README.md).

```shell
python libvdiff.py -o freetype -e co -c -a
```

- `-o/--oss` the OSS project to test, `-l/--lib` the library of it to test (only needed for
  projects providing more than one library)
- `-e/--exp` the experiment, i.e. which compilation settings the compared builds differ in:
  `co` optimization, `ca` architecture, `cc` compiler, `cb` both architecture and optimization,
  `cx` every pair of variants the library was built with
- `-v/--variant` the base variant of the experiment, e.g. `gcc_13_x86_64_O2`. Every experiment
  except `cx` holds the settings it is not exercising fixed at this variant's values, so `co`
  above compares the builds of one compiler and one architecture against each other. Defaults to
  the `DEFAULT_VARIANT` of `data_process/utils/dataset_layout.py`, currently
  `clang_22_arm64_64_O2`; a library that was not built as the base variant is an error rather
  than a reason to pick another one.
- `-c/--cvf` and `-a/--apf` turn the two filters on

Results are written to `saved/libvdiff_idf_all_res`, one CSV per experiment, base variant and
filter combination. Only architectures the pipeline supports take part; PPC and 32-bit X86 builds
are skipped for now.

## IDA Pro install

- IDA Pro 7.5+ on linux: 

  - Make sure the IDA Python switches to python3

  - Extra python packages are required to install for IDA Python: `PATH_TO_IDA_PYTHON -m pip install cptools==2.0.1 networkx==2.4"`

  - Switch IDA's Python to the one used by the LibvDiff environment.
