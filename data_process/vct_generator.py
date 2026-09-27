#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Generate version coordinate table(VCT)
"""
from pathlib import Path
import pandas as pd
from cptools import LogHandler

from argparse import ArgumentParser
from utils.bindiff_types import parse_variant
from utils.dataset_layout import (DEFAULT_VARIANT, iter_library_dirs, iter_version_dirs,
                                  resolve_variant_dir)
from utils.tool_function import read_json


class VCTGenerator(object):
    """
    Generate VCT based on version diff and func similarity model
    """

    def __init__(self, ):
        self.logger = LogHandler('VCTGenerator')

    @staticmethod
    def calculate_vc(vd_add, vd_delete, tgt_exports, ):
        tgt_exports = set(tgt_exports)
        # calculate rvg for func with names (add, delete)
        matched_add = tgt_exports.intersection(vd_add)
        matched_delete = tgt_exports.intersection(vd_delete)
        return len(matched_add), len(matched_delete)

    def run(self, oss, src_code_path, basic_feat_dir, version_diff_path, variant=None):
        """
        Generate VCT based on oss and its lib
        :param variant: the library variant to read the exports of every version with, defaults
            to DEFAULT_VARIANT. A version that was not built as it aborts the run
        :return:
        """
        self.logger.info(f'Start VCT generation for {oss}')
        for lib_path in iter_library_dirs(basic_feat_dir):
            datas = []
            lib = lib_path.name
            func_diffs = read_json(version_diff_path.joinpath(f'vp_diffs-func-{lib}.json'))
            sorted_versions = read_json(version_diff_path.parent.joinpath('sorted_versions.json'))
            version2index = {version: i for i, version in enumerate(sorted_versions)}
            vd_add, vd_delete, _ = func_diffs[f"{sorted_versions[0]}@{sorted_versions[-1]}"]
            vd_add, vd_delete = set(vd_add), set(vd_delete)
            for version, ver_path in iter_version_dirs(lib_path, versions=sorted_versions):
                variant_path = resolve_variant_dir(ver_path, variant)
                exports = read_json(variant_path.joinpath('func_names.json'))['exports']
                vc_x, vc_y = self.calculate_vc(vd_add, vd_delete, exports)
                datas.append((version, vc_x, vc_y, version2index[version]))
            df_vct = pd.DataFrame(datas, columns=[
                'version', 'vc_x', 'vc_y', 'ver_index']).sort_values(by='ver_index').set_index('version')
            df_vct.to_csv(version_diff_path.joinpath(f'vct-{lib}.csv'))


def main():
    vct_generator = VCTGenerator()
    args = ArgumentParser()
    args.add_argument('-o', '--oss', default='freetype', help='oss')
    args.add_argument('-v', '--variant', default=None,
                      help='library variant to read the exports of every version with '
                           '(<compiler>_<compiler_version>_<arch>_<bitness>_<optimization>, '
                           f'e.g. gcc_13_x86_64_O0), defaults to {DEFAULT_VARIANT}')
    arg = args.parse_args()

    vct_generator.run(oss=arg.oss, src_code_path=Path(f'features/{arg.oss}/{arg.oss}-code'),
                      basic_feat_dir=Path(f'dataset/{arg.oss}'),
                      version_diff_path=Path(f'features/{arg.oss}/version-diff'),
                      variant=parse_variant(arg.variant) if arg.variant else None)


if __name__ == '__main__':
    main()
