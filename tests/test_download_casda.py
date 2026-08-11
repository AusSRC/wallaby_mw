import pytest
from astropy.table import Table

from download_casda import build_adql_query, select_milkyway_row


def test_build_adql_query_filters_by_sbid():
    query = build_adql_query('ASKAP-84447')
    assert "obs_id = 'ASKAP-84447'" in query
    assert 'ivoa.obscore' in query


def test_build_adql_query_does_not_alter_the_given_sbid():
    query = build_adql_query('ASKAP-00084447')
    assert "obs_id = 'ASKAP-00084447'" in query


def make_table(rows):
    return Table(rows=rows, names=['filename', 'dataproduct_subtype', 'obs_id'])


def test_select_milkyway_row_picks_the_non_contsub_spectral_cube():
    table = make_table([
        ('weights.i.SB84447.cube.MilkyWay.fits', 'spectral.weight.3d', 'ASKAP-84447'),
        ('image.i.WALLABY_1608-37A.SB84447.cont.taylor.0.restored.conv.fits', 'cont.restored.t0', 'ASKAP-84447'),
        ('image.restored.i.SB84447.cube.MilkyWay.fits', 'spectral.restored.3d', 'ASKAP-84447'),
        ('image.restored.i.SB84447.cube.MilkyWay.contsub.fits', 'spectral.restored.3d', 'ASKAP-84447'),
    ])

    row = select_milkyway_row(table, contsub=False)

    assert row['filename'] == 'image.restored.i.SB84447.cube.MilkyWay.fits'


def test_select_milkyway_row_picks_the_contsub_variant_when_requested():
    table = make_table([
        ('image.restored.i.SB84447.cube.MilkyWay.fits', 'spectral.restored.3d', 'ASKAP-84447'),
        ('image.restored.i.SB84447.cube.MilkyWay.contsub.fits', 'spectral.restored.3d', 'ASKAP-84447'),
    ])

    row = select_milkyway_row(table, contsub=True)

    assert row['filename'] == 'image.restored.i.SB84447.cube.MilkyWay.contsub.fits'


def test_select_milkyway_row_raises_when_no_match():
    table = make_table([
        ('image.i.WALLABY_1608-37A.SB84447.cont.taylor.0.fits', 'cont.cleanmodel.t0', 'ASKAP-84447'),
    ])
    with pytest.raises(Exception):
        select_milkyway_row(table, contsub=False)


def test_select_milkyway_row_raises_when_ambiguous():
    table = make_table([
        ('image.restored.i.SB84447.cube.MilkyWay.fits', 'spectral.restored.3d', 'ASKAP-84447'),
        ('image.restored.i.SB84447.cube.MilkyWay.dup.fits', 'spectral.restored.3d', 'ASKAP-84447'),
    ])
    with pytest.raises(Exception):
        select_milkyway_row(table, contsub=False)
