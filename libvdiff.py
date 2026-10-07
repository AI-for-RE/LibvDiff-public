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


def prepare_features(lib_path, options, model_id, versions=None):
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
            option2ver2bin_feats[str(variant)][version] = load_bin_features(variant_path, model_id)
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


def make_option_pairs(exp, variants):
    """
    Build the (base option, target option) pairs an experiment compares.
    """
    all_options = []
    if exp == "SO+SA":
        # Same optimization and architecture, cross-everything-else
        for base in variants:
            for target in variants:
                if base.optimization != target.optimization:
                    continue
                if (base.arch, base.bit) != (target.arch, target.bit):
                    continue
                if str(base) == str(target):
                     continue
                all_options.append((str(base), str(target)))
    elif exp == "XO+SA":
        # Cross-optimization (compare with O2 as reference) and same architecture
        for base in variants:
            for target in variants:
                if base.optimization != "O2":
                    continue
                if (base.arch, base.bit) != (target.arch, target.bit):
                    continue
                if str(base) == str(target):
                    continue
                all_options.append((str(base), str(target)))
    elif exp == "XO+XA":
        # Cross-optimization and cross-architecture
        for base in variants:
            for target in variants:
                if base.optimization != "O2":
                    continue
                if str(base) == str(target):
                    continue
                all_options.append((str(base), str(target)))

    return all_options


def prepare_features_and_options(versions, lib_path, exp, model_id):
    variants = list_variants(lib_path, versions)
    if not variants:
        raise FileNotFoundError(f'can not find any supported library variant in {lib_path}')
    all_options = make_option_pairs(exp, variants)
    used_options = {option for pair in all_options for option in pair}
    print(f'[+] comparing over {len(all_options)} option pairs')
    option2ver2bin_feats = prepare_features(lib_path, used_options, model_id, versions=versions)
    return option2ver2bin_feats, all_options


def resolve_targets(oss=None, lib=None):
    """
    Build the (oss, library path) pairs to evaluate.

    With `oss`, this is the single library resolved from `oss` and `lib`. Without it, every
    project in the dataset contributes the library resolved for it with lib=None; projects
    whose library can not be resolved that way are skipped.
    """
    if oss is not None:
        return [(oss, resolve_lib(oss, lib))]
    targets = []
    for oss_path in sorted(DATASET_PATH.iterdir()):
        if oss_path.name.startswith('.') or not oss_path.is_dir():
            continue
        try:
            targets.append((oss_path.name, resolve_lib(oss_path.name)))
        except (FileNotFoundError, ValueError) as e:
            print(f'[-] warning! skipping {oss_path.name}: {e}')
    return targets


def evaluate_library(oss, lib_path, cvf, apf, exp, model_id, bcsd_model):
    lib = lib_path.name
    print(f"oss:{oss}, lib: {lib}, cvf: {cvf}, apf: {apf}, exp:{exp}")
    sorted_versions = read_json(FEATURE_PATH.joinpath(f"{oss}/sorted_versions.json"))
    option2ver2bin_feats, all_options = prepare_features_and_options(sorted_versions, lib_path,
                                                                             exp, model_id)
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
                                            bcsd_model=bcsd_model
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

            idf_datas.append((oss, lib, base_option, pred_option, true_version, pred_version,
                              int(true_version == pred_version), time_cost))

    library_precision = true_num / total_num if total_num else 0.0
    print(f'Finished {oss}-{lib}, precision:{library_precision:.3f}')
    return idf_datas


def main(oss, cvf, apf, exp, model_id, lib=None):
    targets = resolve_targets(oss, lib)
    if not targets:
        print('[-] no libraries to evaluate')
        return
    print(f'[+] evaluating {len(targets)} libraries: '
          f'{", ".join(f"{oss}-{lib_path.name}" for oss, lib_path in targets)}')
    bcsd_model = load_model(model_id)

    idf_datas = []
    for target_oss, lib_path in targets:
        idf_datas.extend(evaluate_library(target_oss, lib_path, cvf, apf, exp, model_id, bcsd_model))

    df_idf_res = pd.DataFrame(idf_datas, columns=['oss', 'library', 'reference_variant', 'target_variant',
                                                  'true_version', 'pred_version', 'success', 'time_cost'])
    if oss is not None:
        save_name_prefix = f"{exp}@{oss}_{targets[0][1].name}"
    else:
        save_name_prefix = f"{exp}@all"

    if apf and cvf:
        save_name_prefix += f"@apf@cvf"
    elif apf and not cvf:
        save_name_prefix += f"@apf@no_cvf"
    elif not apf and cvf:
        save_name_prefix += f"@no_apf@cvf"
    else:
        save_name_prefix += f"@no_apf@no_cvf"

    df_idf_res.to_csv(f'{SAVE_DIR}/{save_name_prefix}@idf_res.csv', index=False)

    if not df_idf_res.empty:
        print(df_idf_res.groupby(['oss', 'library'])['success'].mean().rename('precision').to_string())
        print(f'Finished, overall precision:{df_idf_res["success"].mean():.3f}')


if __name__ == '__main__':
    parser = ArgumentParser()
    CVF_ON = None
    AP_ON = None

    parser.add_argument('-o', '--oss', default=None,
                        help='specify OSS to test, defaults to every OSS in the dataset')
    parser.add_argument('-l', '--lib', default=None,
                        help='specify the library of the OSS to test, required for OSS projects '
                             'providing more than one library (requires --oss)')
    parser.add_argument('-c', '--cvf', action='store_true', help='Turn on cvf')
    parser.add_argument('-a', '--apf', action='store_true', help='Turn on apf')
    parser.add_argument('-e', '--exp', default='SO+SA', choices=["SO+SA", "XO+SA", "XO+XA"],
                        help='Experiment')
    parser.add_argument('-m', '--model', default='Asteria', help='specify BCSD model ID')

    args = parser.parse_args()
    if args.lib is not None and args.oss is None:
        parser.error('--lib requires --oss')
    if CVF_ON is not None:
        args.cvf = CVF_ON
    if AP_ON is not None:
        args.apf = AP_ON

    main(oss=args.oss, cvf=args.cvf, apf=args.apf, exp=args.exp, lib=args.lib,
         model_id=args.model)
