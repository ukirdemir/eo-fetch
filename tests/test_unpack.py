import bz2
import gzip
import zipfile

import pytest

from eo_fetch import checkreaders
from eo_fetch.readers import NoReaderError, detect_format, open_data, resolve
from eo_fetch.readers.unpack import sniff, unpacked_dir


def make_netcdf(path):
    xr = pytest.importorskip("xarray")
    pytest.importorskip("netCDF4")
    xr.Dataset({"t": (("x",), [1.0, 2.0])}).to_netcdf(path)
    return path.read_bytes()


def test_sniff_kinds(tmp_path):
    cases = {
        b"PK\x03\x04rest": "zip",
        b"\x1f\x8brest": "gzip",
        b"BZh9rest": "bzip2",
        b"GRIB....": "grib",
        b"\x89HDF\r\n\x1a\n": "hdf5",
        b"CDF\x01....": "netcdf",
        b"hello": None,
    }
    for index, (head, expected) in enumerate(cases.items()):
        path = tmp_path / f"f{index}"
        path.write_bytes(head)
        assert sniff(path) == expected


def test_extensionless_netcdf4_is_found_by_content(tmp_path):
    data = make_netcdf(tmp_path / "ref.nc")
    bare = tmp_path / "PRODUCT_WITHOUT_EXTENSION"
    bare.write_bytes(data)
    assert [name for name, _ in resolve(bare)] == ["hdf5"]
    assert "t" in open_data(bare)


def test_gzip_and_bzip2_are_unpacked(tmp_path):
    data = make_netcdf(tmp_path / "ref.nc")
    gz = tmp_path / "a.nc.gz"
    gz.write_bytes(gzip.compress(data))
    bz = tmp_path / "b.nc.bz2"
    bz.write_bytes(bz2.compress(data))
    for path in (gz, bz):
        assert "t" in open_data(path)
        assert (unpacked_dir(path) / path.name.rsplit(".", 1)[0]).is_file()


def test_zip_with_one_netcdf(tmp_path):
    data = make_netcdf(tmp_path / "ref.nc")
    archive = tmp_path / "PRODUCT"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("inner/data.nc", data)
        zf.writestr("manifest.xml", b"<x/>")
    assert [name for name, _ in resolve(archive)] == ["netcdf"]
    assert "t" in open_data(archive)


def test_zip_with_nat_is_seviri(tmp_path):
    archive = tmp_path / "MSG3-SEVI-MSG15-0100-NA-20261031224242.225000000Z-NA"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("MSG3-SEVI-MSG15-0100-NA-20261031224242.225000000Z-NA.nat", b"x")
    assert resolve(archive) == [("seviri", archive)]


def test_zip_with_other_nat_is_not_seviri(tmp_path):
    archive = tmp_path / "ASCA_SMO_02_M01_20250715073900Z"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ASCA_SMO_02_M01_20250715073900Z.nat", b"x")
    assert resolve(archive) == []


def test_seviri_l2_grib_and_ascii_grid_names():
    assert detect_format("MSG3-SEVI-MSGCLMK-0100-0100-20261031201500.000000000Z-NA.grb") == (
        "seviri-l2"
    )
    assert detect_format("MSG3-SEVI-MSGCLTH-0100-0100-20261031234500.000000000Z-NA.grb") == (
        "seviri-l2"
    )
    assert detect_format("grids_germany_seasonal_sunshine_duration_195316.asc") == "geotiff"


def test_fci_detection(tmp_path):
    name = "W_XX-EUMETSAT-Darmstadt,IMG+SAT,MTI1+FCI-1C-RRAD-FDHSI-FD--CHK-BODY--x_C_EUMT_1.nc"
    assert detect_format(name) == "fci"
    archive = tmp_path / "PRODUCT"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, b"x")
    assert resolve(archive) == [("fci", archive)]


def test_unpacked_dir_is_short_for_long_names(tmp_path):
    long_name = "W_XX-EUMETSAT-Darmstadt_" + "X" * 150
    assert len(str(unpacked_dir(tmp_path / long_name))) < 120


def test_zip_with_unreadable_content_lists_it(tmp_path):
    archive = tmp_path / "PRODUCT.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("data.bufr", b"BUFR")
    with pytest.raises(NoReaderError, match=r"data\.bufr"):
        open_data(archive)


def test_is_data_filters_documentation():
    assert not checkreaders.is_data("index.html")
    assert not checkreaders.is_data("gfs.t00z.pgrb2.0p25.f000.idx")
    assert not checkreaders.is_data("readme.txt")
    assert not checkreaders.is_data("content.log.bz2")
    assert checkreaders.is_data("icon_2026110300_000.grib2.bz2")
    assert checkreaders.is_data("20261103-030419-001-S")
