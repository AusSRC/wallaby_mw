#!/usr/bin/env python3

"""
Download a WALLABY Milky Way spectral cube from CASDA for a given SBID.

Used as the first step of the "from SBID" pipeline: replaces manually staging
a pre-combined wallaby_image with an automated per-SBID CASDA fetch.
"""

import os
import sys
import logging
from argparse import ArgumentParser

import keyring
from keyrings.alt.file import PlaintextKeyring
from astroquery.casda import Casda
from astroquery.utils.tap.core import TapPlus


logging.basicConfig(level=logging.INFO)

TAP_URL = 'https://casda.csiro.au/casda_vo_tools/tap'
KEYRING_SERVICE = 'astroquery:casda.csiro.au'
DEFAULT_KEYRING_FILE = '~/.casda_keyring'


def build_adql_query(sbid):
    """Build the ADQL query selecting all obscore rows for a given SBID.

    `sbid` is used verbatim as the obscore `obs_id` (e.g. 'ASKAP-84447') -
    it is not reformatted or stripped of its prefix.
    """
    return (
        "SELECT filename, dataproduct_subtype, obs_id, access_url "
        "FROM ivoa.obscore "
        f"WHERE obs_id = '{sbid}'"
    )


def select_milkyway_row(table, contsub=False):
    """Pick the single Milky Way spectral cube row out of an SBID's data products."""
    mask = (
        (table['dataproduct_subtype'] == 'spectral.restored.3d')
        & [('MilkyWay' in fname) for fname in table['filename']]
        & [(('contsub' in fname) == contsub) for fname in table['filename']]
    )
    matches = table[mask]
    if len(matches) == 0:
        raise Exception('No Milky Way spectral cube found for this SBID')
    if len(matches) > 1:
        raise Exception(
            f'More than 1 Milky Way spectral cube matched: {list(matches["filename"])}. '
            'Edge case to handle...'
        )
    return matches[0]


def resolve_keyring_path(keyring_file):
    """Expand a configured keyring file path, falling back to DEFAULT_KEYRING_FILE."""
    return os.path.abspath(os.path.expanduser(keyring_file or DEFAULT_KEYRING_FILE))


def authenticate(username, password, keyring_file=None):
    """Authenticate with CASDA, persisting the password in a plaintext keyring file.

    The default OS keyring backend has no working implementation in a
    headless CANFAR container (no dbus/keychain), so `Casda.login()`'s
    normal keyring/getpass password lookup would fail. This points
    `keyring` at an explicit PlaintextKeyring file instead - stored under
    the user's CANFAR home directory (`keyring_file`) so it persists
    across job containers.
    """
    keyring_path = resolve_keyring_path(keyring_file)
    os.makedirs(os.path.dirname(keyring_path), exist_ok=True)
    backend = PlaintextKeyring()
    backend.file_path = keyring_path
    keyring.set_keyring(backend)
    keyring.set_password(KEYRING_SERVICE, username, password)

    authenticated = Casda.login(username=username)
    if not authenticated:
        raise Exception(f'CASDA authentication failed for user {username}')


def query_milkyway_cube(sbid, contsub=False):
    tap = TapPlus(url=TAP_URL)
    job = tap.launch_job_async(build_adql_query(sbid))
    table = job.get_results()
    return select_milkyway_row(table, contsub=contsub)


def download_milkyway_cube(sbid, output_file, contsub=False):
    row = query_milkyway_cube(sbid, contsub=contsub)
    logging.info(f'Staging {row["filename"]} for SBID {sbid}')

    from astropy.table import Table
    staging_table = Table(rows=[row], names=row.colnames)
    urls = Casda.stage_data(staging_table)

    outdir = os.path.dirname(output_file) or '.'
    os.makedirs(outdir, exist_ok=True)
    downloaded = Casda.download_files(urls, savedir=outdir)

    if not downloaded:
        raise Exception('CASDA download returned no files')
    os.replace(downloaded[0], output_file)
    return output_file


def main(argv):
    parser = ArgumentParser()
    parser.add_argument('-s', '--sbid', type=str, required=True, help="ASKAP SBID, e.g. 'ASKAP-84447'")
    parser.add_argument('-o', '--output', type=str, required=True, help='Output fits file path')
    parser.add_argument(
        '--contsub', action='store_true', default=False,
        help='Download the continuum-subtracted variant of the Milky Way cube'
    )
    args = parser.parse_args(argv)

    username = os.environ.get('CASDA_USERNAME')
    password = os.environ.get('CASDA_PASSWORD')
    keyring_file = os.environ.get('CASDA_KEYRING_FILE')
    assert username, 'CASDA_USERNAME environment variable must be set'
    assert password, 'CASDA_PASSWORD environment variable must be set'
    authenticate(username, password, keyring_file=keyring_file)

    if os.path.exists(args.output):
        logging.info(f'File {args.output} already exists. Skipping download.')
        return args.output

    download_milkyway_cube(args.sbid, args.output, contsub=args.contsub)
    logging.info(f'Downloaded SBID {args.sbid} Milky Way cube to {args.output}')


if __name__ == '__main__':
    main(sys.argv[1:])
