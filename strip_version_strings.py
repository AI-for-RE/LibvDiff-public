"""
Remove every string that mentions a version of the binary's library from its strings.json.

Usage: python3 strip_version_strings.py <dataset> [--apply]

Without --apply this only reports how many strings would be removed. With --apply each
strings.json is first copied to strings_old.json next to it, and the run refuses to start
if any strings_old.json already exists.

The versions of a library are the ones it has in the dataset, parsed from its version
directory names (<dataset>/<oss>/<library>/<version>/<variant>/strings.json), e.g.
curl-8_11_0 -> 8.11.0, VER-2-9-1 -> 2.9.1, v1.3 -> 1.3. Every binary of the library is
stripped of all of them, not only of its own version, so e.g. libfreetype.so.2.8 is also
removed from the 2.8.1 binaries. A string matches when it contains one of those dotted
versions not directly adjacent to further version components, so 1.2.1 does not match
1.2.10, 1.3.1 does not match 1.3.1.2 and 1.3 does not match %1.3f, while suffixes like
8.11.0-DEV, 1.3.1.2-audit and libwebp-v1.2.0_gcc still match. Versions of other libraries,
such as the zlib version linked into libcurl or GLIBC_2.17, are left alone.
"""
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

VERSION_IN_DIR = re.compile(r'\d+(?:[._-]\d+)*')


def version_forms(library, parts):
    """The spellings of a version that appear in the library's binaries."""
    forms = ['.'.join(parts)]
    if library == 'libxml2' and len(parts) == 3:
        # LIBXML_VERSION_STRING, e.g. 2.13.4 -> 21304
        major, minor, patch = map(int, parts)
        forms.append(f'{major}{minor:02d}{patch:02d}')
    return forms


def version_pattern(library, version_dirs):
    """Matches any of the given versions of the library."""
    forms = set()
    for version_dir in version_dirs:
        match = VERSION_IN_DIR.search(version_dir)
        if match is None:
            sys.exit(f'can not parse a version out of {version_dir}')
        forms.update(version_forms(library, re.split(r'[._-]', match.group())))
    alternatives = '|'.join(re.escape(form) for form in sorted(forms, key=len, reverse=True))
    # not preceded by a digit or "<digit>.", not followed by an alphanumeric or ".<digit>"
    return re.compile(rf'(?<!\d)(?<!\d\.)(?:{alternatives})(?![0-9A-Za-z]|\.\d)')


dataset = Path(sys.argv[1])
apply = '--apply' in sys.argv

paths = sorted(dataset.rglob('strings.json'))
lib2version_dirs = defaultdict(set)
for path in paths:
    _, lib, version_dir = path.relative_to(dataset).parts[:3]
    lib2version_dirs[lib].add(version_dir)
lib2pattern = {lib: version_pattern(lib, version_dirs) for lib, version_dirs in lib2version_dirs.items()}
if apply:
    existing = [p.with_name('strings_old.json') for p in paths if p.with_name('strings_old.json').exists()]
    if existing:
        sys.exit(f'refusing to overwrite {len(existing)} existing strings_old.json, e.g. {existing[0]}')

per_lib = defaultdict(lambda: {'files': 0, 'all': 0, 'rodata': 0})
not_roundtrip = []
for path in paths:
    lib = path.relative_to(dataset).parts[1]
    pattern = lib2pattern[lib]
    text = path.read_text()
    data = json.loads(text)
    if json.dumps(data, indent=4, sort_keys=True) != text:
        not_roundtrip.append(path)
    removed = {}
    for key in ('strings_all', 'strings_in_rodata'):
        kept = [s for s in data[key] if not pattern.search(s)]
        removed[key] = len(data[key]) - len(kept)
        data[key] = kept
    stats = per_lib[lib]
    stats['files'] += 1
    stats['all'] += removed['strings_all']
    stats['rodata'] += removed['strings_in_rodata']
    if apply:
        shutil.copy2(path, path.with_name('strings_old.json'))
        with path.open('wt') as handle:
            json.dump(data, handle, indent=4, sort_keys=True)

print(f'files not byte-identical on round-trip: {len(not_roundtrip)}')
for p in not_roundtrip[:5]:
    print('  ', p)
print(f"{'lib':<12}{'files':>6}{'avg strings_all':>18}{'avg rodata':>12}")
for lib, s in sorted(per_lib.items()):
    print(f"{lib:<12}{s['files']:>6}{s['all'] / s['files']:>18.2f}{s['rodata'] / s['files']:>12.2f}")
