#!/usr/bin/python3
# -*- coding: utf-8 -*-
import time
import warnings

import sys
from argparse import ArgumentParser

sys.path.append('data_process')
warnings.filterwarnings('ignore')
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict

import pandas as pd

from data_process.vct_generator import VCTGenerator
from data_process.utils.bindiff_types import parse_variant
from data_process.utils.data_prepare import load_bin_features
from data_process.utils.dataset_layout import (DEFAULT_VARIANT, iter_variant_dirs, iter_version_dirs,
                                               list_variants, resolve_library_dir)
from data_process.utils.tool_function import read_json
from data_process.feat_encoding import load_model

from version_identifier import check_version_by_constant_rvg, check_version_by_rvg2, version_range_locating

DATASET_PATH = Path('data_process/dataset/')
FEATURE_PATH = Path('data_process/features')

OSS2LIB = {
    'aws-c-common': 'libaws-c-common',
    'c-blosc': 'libblosc',
    'expat': 'libexpat',
    'freetype': 'libfreetype',
    'mbedtls': 'libmbedcrypto',
    'libpng': 'libpng',
    'libxml2': 'libxml2',
    'zlib': 'libz',
    'openssl': 'libcrypto',
}

SAVE_DIR = Path('saved/libvdiff_idf_all_res')
SAVE_DIR.mkdir(exist_ok=True, parents=True)


def prepare_features(lib_path, options, versions=None):
    """
    Load the binary features of every requested variant of every requested version.

    An option is the ID of a library variant directory, i.e. str(Variant), for example
    'gcc_13_x86_64_O2'. Every requested version has to have been built as every requested
    option, so that the experiment compares the same builds over all of them.
    """
    option2ver2bin_feats = defaultdict(dict)

    options = set(options)
    for version, version_path in iter_version_dirs(lib_path, versions):
        built = set()
        for variant, variant_path in iter_variant_dirs(version_path):
            if str(variant) not in options:
                continue
            built.add(str(variant))
            option2ver2bin_feats[str(variant)][version] = load_bin_features(variant_path)
        missing = options.difference(built)
        if missing:
            raise FileNotFoundError(f'{lib_path.name}-{version} was not built as '
                                    f'{", ".join(sorted(missing))}')
    return option2ver2bin_feats


def resolve_lib(oss, lib=None):
    """
    Locate the directory of the library to identify versions of.

    The OSS2LIB mapping is only a hint: a project may ship its library under a different name
    (libpng builds libpng16, for instance), in which case the library is resolved from the
    dataset instead.
    """
    oss_path = DATASET_PATH.joinpath(oss)
    if lib:
        return resolve_library_dir(oss_path, lib)
    try:
        return resolve_library_dir(oss_path, OSS2LIB.get(oss))
    except FileNotFoundError:
        return resolve_library_dir(oss_path)


def load_vd(oss, lib):
    vd_func_path = FEATURE_PATH.joinpath(f"{oss}/version-diff/vp_diffs-func-{lib}.json")
    vd_str_path = FEATURE_PATH.joinpath(f"{oss}/version-diff/vp_diffs-str-{lib}.json")
    try:
        func_diffs = read_json(vd_func_path)
    except FileNotFoundError:
        print(f'[-] warning! can not find func diffs of {oss}-{lib}')
        func_diffs = {}
    try:
        str_diffs = read_json(vd_str_path)
    except FileNotFoundError:
        print(f'[-] warning! can not find func diffs of {oss}-{lib}')
        str_diffs = {}
    return func_diffs, str_diffs


def make_option_pairs(exp, base_variant, variants):
    """
    Build the (base option, target option) pairs an experiment compares.

    Every experiment except cross_all is anchored on `base_variant`: it holds the variance
    attributes the experiment is not exercising fixed at that variant's values, so e.g.
    cross_optim compares builds of one compiler and one architecture against each other.
    """
    if exp == "cross_optim":
        # Same compiler and architecture, every combination of two optimization levels
        candidates = [variant for variant in variants
                      if (variant.compiler, variant.compiler_version) == (base_variant.compiler,
                                                                          base_variant.compiler_version)
                      and (variant.arch, variant.bit) == (base_variant.arch, base_variant.bit)]
        distinguisher = lambda variant: variant.optimization
    elif exp == "cross_arch":
        # Same compiler and optimization level, every combination of two architectures
        candidates = [variant for variant in variants
                      if (variant.compiler, variant.compiler_version) == (base_variant.compiler,
                                                                          base_variant.compiler_version)
                      and variant.optimization == base_variant.optimization]
        distinguisher = lambda variant: (variant.arch, variant.bit)
    elif exp == "cross_compiler":
        # Same architecture and optimization level, every combination of two compilers
        candidates = [variant for variant in variants
                      if (variant.arch, variant.bit) == (base_variant.arch, base_variant.bit)
                      and variant.optimization == base_variant.optimization]
        distinguisher = lambda variant: (variant.compiler, variant.compiler_version)
    elif exp == "cross_all":
        # Every combination of two variants, whichever attributes they differ in
        candidates = list(variants)
        distinguisher = lambda variant: str(variant)
    else:
        # base_compare: the base variant against all variant builds
        return [(str(base_variant), str(variant)) for variant in variants]

    all_options = []
    for base in candidates:
        for target in candidates:
            if distinguisher(base) == distinguisher(target):
                continue
            all_options.append((str(base), str(target)))
    return all_options


def prepare_features_and_options(versions, lib_path, exp, base_variant=None):
    variants = list_variants(lib_path, versions)
    if not variants:
        raise FileNotFoundError(f'can not find any supported library variant in {lib_path}')
    if base_variant is None:
        base_variant = DEFAULT_VARIANT
    if not any(variant == base_variant for variant in variants):
        available = ', '.join(str(variant) for variant in variants)
        raise FileNotFoundError(f'can not find variant {base_variant} in {lib_path}, '
                                f'available variants: {available}')

    all_options = make_option_pairs(exp, base_variant, variants)
    if not all_options:
        raise ValueError(f'{exp} needs library variants differing from the base variant '
                         f'{base_variant}, none of the variants built qualify')
    used_options = {option for pair in all_options for option in pair}
    print(f'[+] base variant: {base_variant}, comparing {len(used_options)} variants '
          f'over {len(all_options)} option pairs')
    option2ver2bin_feats = prepare_features(lib_path, used_options, versions=versions)
    return option2ver2bin_feats, all_options, base_variant


def main(oss, cvf, apf, exp, lib=None, variant=None):
    lib_path = resolve_lib(oss, lib)
    lib = lib_path.name
    Asteria = load_model()
    print(f"oss:{oss}, lib: {lib}, cvf: {cvf}, apf: {apf}, exp:{exp}")
    sorted_versions = read_json(FEATURE_PATH.joinpath(f"{oss}/sorted_versions.json"))
    option2ver2bin_feats, all_options, variant = prepare_features_and_options(sorted_versions, lib_path,
                                                                             exp, base_variant=variant)
    all_vd_func, all_vd_str = load_vd(oss=oss, lib=lib)
    try:
        df_vct = pd.read_csv(FEATURE_PATH.joinpath(f'{oss}/version-diff/vct-{lib}.csv'), index_col=0)
    except FileNotFoundError:
        print(f'[-] warning can not find vct of {oss}-{lib}')
        df_vct = None

    # sorted_versions = sorted(list(allow_versions))
    idf_datas = []
    true_num = 0
    total_num = 0
    func_add_max, func_delete_max, _ = all_vd_func[f"{sorted_versions[0]}@{sorted_versions[-1]}"]
    for base_option, pred_option in all_options:
        bar = tqdm(sorted_versions)
        for true_version in bar:
            start = time.time()

            if cvf and df_vct is not None:
                vc_x, vc_y = VCTGenerator.calculate_vc(
                    vd_add=func_add_max,
                    vd_delete=func_delete_max,
                    tgt_exports=option2ver2bin_feats[pred_option][true_version]['exports']
                )
                tmp_versions = version_range_locating(vc_x=vc_x, vc_y=vc_y, vct=df_vct)
                cand_versions = [version for version in sorted_versions if version in tmp_versions]
                if len(cand_versions) == 0:
                    cand_versions = sorted_versions
                pred_versions = [cand_versions[0]]
                for cur_version in cand_versions[1:]:
                    func_add, func_delete, func_update = all_vd_func.get(f"{pred_versions[-1]}@{cur_version}",
                                                                         ([], [], []))
                    try:
                        str_add, str_delete, _ = all_vd_str.get(f"{pred_versions[-1]}@{cur_version}", ([], [], []))
                    except ValueError:
                        str_add, str_delete = all_vd_str.get(f"{pred_versions[-1]}@{cur_version}", ([], [],))

                    res = check_version_by_constant_rvg(func_add=set(func_add),
                                                        func_delete=set(func_delete),
                                                        str_add=set(str_add),
                                                        str_delete=set(str_delete),
                                                        old_bin_feats=option2ver2bin_feats[base_option][
                                                            pred_versions[-1]],
                                                        new_bin_feats=option2ver2bin_feats[base_option][cur_version],
                                                        tgt_bin_feats=option2ver2bin_feats[pred_option][true_version])
                    if res['rvg_old'] > res['rvg_new']:
                        pred_versions = [cur_version]
                    elif res['rvg_old'] == res['rvg_new']:
                        pred_versions.append(cur_version)

            else:
                pred_versions = sorted_versions

            pred_version = pred_versions[0]

            for cur_version in pred_versions[1:]:
                func_add, func_delete, func_update = all_vd_func.get(f"{pred_version}@{cur_version}",
                                                                     ([], [], []))
                try:
                    str_add, str_delete, _ = all_vd_str.get(f"{pred_version}@{cur_version}", ([], [], []))
                except ValueError:
                    str_add, str_delete = all_vd_str.get(f"{pred_version}@{cur_version}", ([], [],))
                old_bin_feats = option2ver2bin_feats[base_option][pred_version]
                new_bin_feats = option2ver2bin_feats[base_option][cur_version]

                res = check_version_by_rvg2(func_add=set(func_add),
                                            func_delete=set(func_delete),
                                            func_update=set(func_update),
                                            str_add=set(str_add),
                                            str_delete=set(str_delete),
                                            old_bin_feats=old_bin_feats,
                                            new_bin_feats=new_bin_feats,
                                            tgt_bin_feats=option2ver2bin_feats[pred_option][true_version],
                                            ap_on=apf,
                                            bcsd_model=Asteria
                                            )
                if res['rvg_old'] > res['rvg_new']:
                    pred_version = cur_version

            time_cost = time.time() - start
            if pred_version == true_version:
                print(f'\n[+] source bin option {base_option}, target bin option: {pred_option}, true: {true_version}, predict: {pred_version}')
                true_num += 1
            else:
                print(f'\n[-] source bin option {base_option}, target bin option: {pred_option}, true: {true_version}, predict: {pred_version}')
            total_num += 1
            bar.set_description(
                f'identify {true_version}-{base_option} is {pred_version}-{pred_option}, {true_num / total_num:.3f}')

            idf_datas.append(
                (base_option, pred_option, true_version, pred_version, true_version == pred_version, time_cost))

    df_idf_res = pd.DataFrame(idf_datas, columns=['base_option', 'pred_option', 'true_version', 'pred_version',
                                                  'is_true', 'time_cost'])
    # The base variant is part of the name: an experiment anchored on another one compares
    # different builds and so produces different results
    save_name_prefix = f"{exp}@{oss}_{lib}@{variant}"

    if apf and cvf:
        save_name_prefix += f"@apf@cvf"
    elif apf and not cvf:
        save_name_prefix += f"@apf@no_cvf"
    elif not apf and cvf:
        save_name_prefix += f"@no_apf@cvf"
    else:
        save_name_prefix += f"@no_apf@no_cvf"

    df_idf_res.to_csv(f'{SAVE_DIR}/{save_name_prefix}@idf_res.csv', index=False)

    print(f'Finished, precision:{true_num / total_num:.3f}')


if __name__ == '__main__':
    parser = ArgumentParser()
    CVF_ON = None
    AP_ON = None
    exp_mapping = {
        'co': 'cross_optim',
        'ca': 'cross_arch',
        'cc': 'cross_compiler',
        'cx': 'cross_all',
        'bc': 'base_compare',
    }

    parser.add_argument('-o', '--oss', default='freetype', help='specify OSS to test')
    parser.add_argument('-l', '--lib', default=None,
                        help='specify the library of the OSS to test, required for OSS projects '
                             'providing more than one library')
    parser.add_argument('-v', '--variant', default=None,
                        help='base library variant of the experiment '
                             '(<compiler>_<compiler_version>_<arch>_<bitness>_<optimization>, '
                             f'e.g. gcc_13_x86_64_O2), defaults to {DEFAULT_VARIANT}')
    parser.add_argument('-c', '--cvf', action='store_true', help='Turn on cvf')
    parser.add_argument('-a', '--apf', action='store_true', help='Turn on apf')
    parser.add_argument('-e', '--exp', default='co', choices=sorted(exp_mapping.keys()),
                        help='Experiment (co: cross optimization, ca: cross architecture, '
                             'cc: cross compiler, cb: cross both architecture and optimization, '
                             'cx: cross all variants)')

    args = parser.parse_args()
    if CVF_ON is not None:
        args.cvf = CVF_ON
    if AP_ON is not None:
        args.apf = AP_ON

    main(oss=args.oss, cvf=args.cvf, apf=args.apf, exp=exp_mapping[args.exp], lib=args.lib,
         variant=parse_variant(args.variant) if args.variant else None)
