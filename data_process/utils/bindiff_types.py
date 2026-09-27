from __future__ import annotations

import os
from dataclasses import dataclass

# A single point in the space of compilation settings.
#
# NOTE: The field names here are used as strings elsewhere -- they must stay in sync with
# VALID_CATEGORIES in tasks/analyze.py, and with the `analysis_categories` values that users
# write in the config, because the analyze task looks categories up via asdict(variant)[category].
@dataclass
class Variant:
    compiler: str
    compiler_version: str
    optimization: str
    arch: str
    bit: int

    def __str__(self) -> str:
        return f"{self.compiler}_{self.compiler_version}_{self.arch}_{self.bit}_{self.optimization}"

    def to_hermessim(self) -> str:
        # Note: HermesSim doesn't have a notion of bitness
        # (we don't even use this field anyways but include it for compatibility with binary_function_similarity repo)
        return f"{self.arch}-{self.compiler}-{self.compiler_version}-{self.optimization}"

    def __eq__(self, other) -> bool:
        return str(self) == str(other)

# The number of Variant fields encoded after the library name/version in a variant ID.
_VARIANT_FIELD_COUNT = 5

# Given the ID of a library variant, parse it into the library name, version string, and Variant.
# Accepts either a bare ID or a path ending in one.
def parse_library_variant(variant_name: str) -> tuple[str, str, Variant]:
    basename = os.path.basename(os.path.normpath(variant_name))
    lib_name, separator, attrs_str = basename.partition("-")
    if not separator:
        raise ValueError(f"Malformed variant ID '{basename}': expected '<library>-<version>_<compiler>_<compiler_version>_<arch>_<bit>_<optimization>'.")
    # Split from the right so a library version containing underscores stays intact.
    # The remaining fields are guarded by validate_variant_naming() at config load.
    attrs = attrs_str.rsplit("_", _VARIANT_FIELD_COUNT)
    if len(attrs) != _VARIANT_FIELD_COUNT+1:
        raise ValueError(f"Malformed variant ID '{basename}': expected {_VARIANT_FIELD_COUNT+1} '_'-separated attributes after '{lib_name}-', found {len(attrs)}.")
    # Order must match to_library_variant's field order.
    version_name, compiler, compiler_version, arch, bit, optimization = attrs
    return lib_name, version_name, Variant(compiler=compiler, arch=arch, bit=int(bit), compiler_version=compiler_version, optimization=optimization)

# Given the name of a variant directory (or a path ending in one), parse the variance
# attributes it encodes. This is the directory-level form of a variant ID: the library name
# and its version live in the parent directories rather than in the name itself, so only the
# Variant fields are present. parse_library_variant() handles the full ID, which is what the
# binaries inside those directories are named with.
def parse_variant(variant_name: str) -> Variant:
    basename = os.path.basename(os.path.normpath(variant_name))
    attrs = basename.split("_")
    if len(attrs) != _VARIANT_FIELD_COUNT:
        raise ValueError(f"Malformed variant '{basename}': expected {_VARIANT_FIELD_COUNT} '_'-separated attributes '<compiler>_<compiler_version>_<arch>_<bit>_<optimization>', found {len(attrs)}.")
    # Order must match Variant.__str__'s field order.
    compiler, compiler_version, arch, bit, optimization = attrs
    if not bit.isdigit():
        raise ValueError(f"Malformed variant '{basename}': bitness '{bit}' is not a number.")
    return Variant(compiler=compiler, arch=arch, bit=int(bit), compiler_version=compiler_version, optimization=optimization)

# Parses a HermesSim library variant.
def parse_library_variant_hermessim(variant_name: str) -> tuple[str, str, Variant]:
    basename = os.path.basename(os.path.normpath(variant_name))
    attrs_str, separator, lib_attrs_str = basename.partition("_")
    if not separator:
        raise ValueError(f"Malformed variant ID '{basename}': expected '<arch>-<compiler>-<compiler_version>-<optimization>_<library>-<version>'.")
    attrs = attrs_str.split("-", 3)
    if len(attrs) != 4:
        raise ValueError(f"Malformed variant ID '{basename}': expected 4 '-'-separated variance attributes, found {len(attrs)}.")
    arch, compiler, compiler_version, optimization = attrs
    lib_attrs = lib_attrs_str.split("-", 1)
    if len(lib_attrs) != 2:
        raise ValueError(f"Malformed library ID '{lib_attrs_str}' in variant ID '{basename}'.")
    lib_name, version_name = lib_attrs

    # Parse out architecture and bitness (janky-ish solution, the architecture names aren't perfect, but this puts it in line with
    # convention from the rest of the codebase)
    if arch == "arm64":
        bit = 64
    elif arch == "arm32":
        arch = "arm64"
        bit = 32
    elif arch == "x64":
        arch = "x86"
        bit = 64
    # 32-bit X86 is not supported at the moment, re-enable this branch when it is.
    # elif arch == "x86":
    #     bit = 32
    elif arch == "mips64":
        arch = "mips"
        bit = 64
    elif arch == "mips32":
        arch = "mips"
        bit = 32
    else:
        raise ValueError(f"Unrecognized architecture '{arch}'.")

    return lib_name, version_name, Variant(compiler=compiler, arch=arch, bit=int(bit), compiler_version=compiler_version, optimization=optimization)

# Inverse of parse_library_variant.
def to_library_variant(lib_name: str, version: str, variant: Variant, hermessim: bool = False) -> str:
    if hermessim:
        return f"{variant.to_hermessim()}_{lib_name}-{version}"
    else:
        return f"{lib_name}-{version}_{str(variant)}"

# Variant IDs are positional strings, so the separators must not appear inside the values
# themselves. Validate config values up front rather than letting parse_library_variant()
# silently mis-split a directory name much later in the pipeline.
def validate_variant_naming(library_names: list[str], optimizations: list[str], toolchains: dict[str, dict[str, list[str]]]) -> None:
    errors = []
    for lib_name in library_names:
        # The library name is split off at the first '-', so it may not contain one.
        if "-" in lib_name:
            errors.append(f"Library name '{lib_name}' contains '-', which separates the library name from its version and variant attributes.")
    # Every other field is '_'-separated. Library versions are exempt: parse_library_variant
    # splits from the right, so underscores there survive the round trip.
    for optimization in optimizations:
        if "_" in optimization:
            errors.append(f"Optimization name '{optimization}' contains '_', which separates variant attributes.")
    for compiler, arch_dict in toolchains.items():
        if "_" in compiler:
            errors.append(f"Compiler '{compiler}' contains '_', which separates variant attributes.")
        for arch, versions in arch_dict.items():
            if "_" in arch:
                errors.append(f"Compiler '{compiler}/{arch}' contains '_', which separates variant attributes.")
            for compiler_version in versions:
                if "_" in compiler_version:
                    errors.append(f"Compiler '{compiler}/{compiler_version}/{arch}' contains '_', which separates variant attributes.")
    if errors:
        raise ValueError("Invalid names in config:\n" + "\n".join(f"  - {e}" for e in errors))

# Returns the first (compiler, arch, compiler_version) triple in config order.
# For tasks that are not investigating compiler variance (e.g. the rewrite tasks, which vary
# only the optimization level) and just need one toolchain to build with. Callers resolve the
# actual compiler binary from the triple via resolve_toolchain in tasks/build.py.
def default_compiler(toolchains: dict[str, dict[str, list[str]]]) -> tuple[str, str, str]:
    for compiler, arch_dict in toolchains.items():
        for arch, versions in arch_dict.items():
            for compiler_version in versions:
                return (compiler, arch, compiler_version)
    raise ValueError("No toolchains defined in the config's compilation_settings.")