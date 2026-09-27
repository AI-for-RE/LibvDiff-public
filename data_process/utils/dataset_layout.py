#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Helpers for walking the binary dataset directory tree.

The layout is:

    <dataset>/<oss>/<library>/<version>/<variant>/<library>-<version>_<variant>.so

where <variant> is `<compiler>_<compiler_version>_<arch>_<bitness>_<optimization>`
(i.e. str(Variant), see utils/bindiff_types.py) and the binary inside is named with the
full library variant ID. Generated features (func_names.json, Asteria_features.pkl, ...)
are written next to the binary, so a variant directory is the unit that
utils/data_prepare.py:load_bin_features() consumes.
"""
from pathlib import Path

from .bindiff_types import Variant, parse_variant

try:
    # data_process scripts are run from within data_process/, so settings is top-level there
    from settings import SKIP_SUFFIX
except ImportError:
    # ... while libvdiff.py imports this module as data_process.utils.dataset_layout
    from ..settings import SKIP_SUFFIX

# The (arch, bitness) pairs the pipeline handles. Variants built for anything else are
# skipped when walking the dataset.
# PPC and 32-bit X86 are not supported at the moment, re-enable these entries when they are.
SUPPORTED_ARCHES = [
    ('x86', 64),
    ('arm64', 64),
    # ('x86', 32),
    # ('ppc', 32),
    # ('ppc', 64),
]

# Optimization levels ordered from least to most optimized, for the order variants are listed
# in. Levels missing from this list sort last (alphabetically among themselves).
OPT_ORDER = ['O0', 'O1', 'O2', 'O3', 'Os', 'Oz', 'Ofast']

# The variant scripts read a library with when the caller does not name one. It is a fixed
# build rather than a pick among the ones available, so that every version of a library is
# read from the same build and two runs over the same dataset read the same one.
DEFAULT_VARIANT = Variant(compiler='clang', compiler_version='22', arch='arm64', bit=64,
                          optimization='O2')


def is_supported(variant: Variant) -> bool:
    """Whether the pipeline handles binaries built for this variant's architecture."""
    return (variant.arch, variant.bit) in SUPPORTED_ARCHES


def variant_sort_key(variant: Variant):
    """Deterministic ordering over variants, least optimized first."""
    try:
        opt_index = OPT_ORDER.index(variant.optimization)
    except ValueError:
        opt_index = len(OPT_ORDER)
    return (opt_index, variant.optimization, -variant.bit, variant.arch,
            variant.compiler, variant.compiler_version)


def iter_library_dirs(oss_path):
    """Yield the library directories of an OSS project directory, sorted by name."""
    oss_path = Path(oss_path)
    if not oss_path.is_dir():
        raise FileNotFoundError(f"can not find OSS project directory {oss_path}")
    for lib_path in sorted(oss_path.iterdir()):
        if lib_path.name.startswith('.') or not lib_path.is_dir():
            continue
        yield lib_path


def resolve_library_dir(oss_path, lib=None):
    """
    Locate the directory of one library of an OSS project.

    Without `lib`, projects providing a single library resolve to it; projects providing
    several require the caller to name one.
    """
    lib_paths = list(iter_library_dirs(oss_path))
    if not lib_paths:
        raise FileNotFoundError(f"OSS project {oss_path} provides no libraries")
    if lib is None:
        if len(lib_paths) > 1:
            names = ', '.join(lib_path.name for lib_path in lib_paths)
            raise ValueError(f"OSS project {oss_path} provides several libraries ({names}), "
                             f"please select one with --lib")
        return lib_paths[0]
    for lib_path in lib_paths:
        if lib_path.name == lib:
            return lib_path
    names = ', '.join(lib_path.name for lib_path in lib_paths)
    raise FileNotFoundError(f"can not find library '{lib}' in {oss_path}, "
                            f"available libraries: {names}")


def iter_version_dirs(lib_path, versions=None):
    """
    Yield (version, path) of the version directories of a library, sorted by name.

    :param versions: if given, only these versions are yielded
    """
    for version_path in sorted(Path(lib_path).iterdir()):
        if version_path.name.startswith('.') or not version_path.is_dir():
            continue
        if versions is not None and version_path.name not in versions:
            continue
        yield version_path.name, version_path


def iter_variant_dirs(version_path, supported_only=True):
    """
    Yield (Variant, path) of the variant directories of one version, in variant sort order.

    Directories whose name is not a variant ID are skipped, as are variants built for an
    architecture the pipeline does not support (see SUPPORTED_ARCHES).
    """
    variants = []
    for variant_path in Path(version_path).iterdir():
        if variant_path.name.startswith('.') or not variant_path.is_dir():
            continue
        try:
            variant = parse_variant(variant_path.name)
        except ValueError:
            continue
        if supported_only and not is_supported(variant):
            continue
        variants.append((variant, variant_path))
    yield from sorted(variants, key=lambda item: variant_sort_key(item[0]))


def list_variants(lib_path, versions=None, supported_only=True):
    """Return the variants a library was built with, in variant sort order."""
    variants = {}
    for _, version_path in iter_version_dirs(lib_path, versions):
        for variant, _ in iter_variant_dirs(version_path, supported_only=supported_only):
            variants[str(variant)] = variant
    return sorted(variants.values(), key=variant_sort_key)


def resolve_variant_dir(version_path, variant=None):
    """
    Locate the directory holding one variant of a version.

    Another variant is never substituted for the one asked for: a run reads every version of a
    library from the same build, so a version that was not built as `variant` raises
    FileNotFoundError instead.

    :param variant: the variant to locate, DEFAULT_VARIANT when not given
    """
    if variant is None:
        variant = DEFAULT_VARIANT
    for candidate, variant_path in iter_variant_dirs(version_path):
        if candidate == variant:
            return variant_path
    raise FileNotFoundError(f'can not find variant {variant} of {version_path}')


def find_binary(variant_path):
    """
    Return the binary inside a variant directory, or None if it holds only generated features.
    """
    for path in sorted(Path(variant_path).iterdir()):
        if path.is_file() and path.suffix not in SKIP_SUFFIX:
            return path
    return None


def iter_binaries(oss_path, lib=None, versions=None):
    """Yield the binaries of an OSS project, one per variant of every version."""
    lib_paths = [resolve_library_dir(oss_path, lib)] if lib else list(iter_library_dirs(oss_path))
    for lib_path in lib_paths:
        for _, version_path in iter_version_dirs(lib_path, versions):
            for _, variant_path in iter_variant_dirs(version_path):
                bin_path = find_binary(variant_path)
                if bin_path is not None:
                    yield bin_path
