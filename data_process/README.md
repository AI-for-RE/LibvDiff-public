# Feature Generation
> It should be noted that we pre generated all features of binaries for experiment purpose. In fact, not all of them are needed to be generated based on our two designed filters. 

In this document, we illustrate how we generate all features in LibvDiff which includes:
- binary features
- version differences 
- version coordinates

## Dataset Layout
Binaries live in `data_process/dataset` under one directory per OSS project, library, version and
library variant:

```
dataset/<oss>/<library>/<version>/<variant>/<library>-<version>_<variant>.so
```

where a variant is the point in the space of compilation settings the binary was built with:

```
<compiler>_<compiler version>_<arch>_<bitness>_<optimization>      e.g. gcc_13_x86_64_O2
```

For example, `dataset/freetype/libfreetype/VER-2-11-0/gcc_13_x86_64_O2/libfreetype-VER-2-11-0_gcc_13_x86_64_O2.so`.
The generated features of a binary are written next to it, inside its variant directory.

Only the versions listed in `features/<oss>/sorted_versions.json` are processed, and only the
architectures listed in `SUPPORTED_ARCHES` (`utils/dataset_layout.py`) are — PPC and 32-bit X86
binaries are skipped for now. `utils/bindiff_types.py` parses and formats variant IDs.

## Binary Features
There are three types of binary features used in LibvDiff:
- basic features: function names (including exports), string literals
- function embeddings
- anchor paths

Two main python scripts are used to generate binary features. Both process every variant of every
version of every library of the OSS, and take an optional `--lib` to restrict them to one library
of a project providing several.
```shell
python feature_generator.py -o freetype  
python feat_encoding.py -o freetype
```

## Version Differences
Before generating version differences, you have to clone the source code of OSS into `data_process/features/OSS-code`. Take freetype as an example,
```shell
git clone https://gitlab.freedesktop.org/freetype/freetype.git data_process/features/freetype/freetype-code
```
Then generate the version differences with `vdcs_generator.py` 
> before running the example, please make sure the source code of OSS and compiled binaries are in the right place. 

```shell
python vdcs_generator.py -o freetype
```

## Version Coordinates
Version coordinates are generated with `vct_generator.py`, you have to generate version differences and basic features at first before generate version coordinates.

```shell
python vct_generator.py -o freetype
```

Both generators read the software level features of one build per version, the same build for
every version of a library. Pass `-v/--variant` to choose which one, e.g. `-v gcc_13_x86_64_O2`;
without it they read the `DEFAULT_VARIANT` of `utils/dataset_layout.py`, currently
`clang_22_arm64_64_O2`. There is no fallback to another build: a version that was not built as
the requested variant aborts the run.
