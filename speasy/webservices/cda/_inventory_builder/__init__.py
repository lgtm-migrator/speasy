from ._xml_catalogs_parser import load_xml_catalog
from ._cdf_masters_parser import update_tree
from ....core.index import index
from ....core.inventory.indexes import SpeasyIndex, to_dict, from_dict
from ....config import cdaweb as cda_cfg
import requests
from tempfile import NamedTemporaryFile
import tarfile
import os
from glob import glob

_MASTERS_CDF_PATH = f"{cda_cfg.inventory_data_path()}/masters_cdf/"
_XML_CATALOG_PATH = f"{cda_cfg.inventory_data_path()}/all.xml"


def _ensure_path_exists(path: str):
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)


def _clean_master_cdf_folder():
    _ensure_path_exists(_MASTERS_CDF_PATH)
    cdf_files = glob(f"{_MASTERS_CDF_PATH}/*.cdf")
    for cdf_file in cdf_files:
        os.remove(cdf_file)


def _download_and_extract_master_cdf(masters_url: str):
    with NamedTemporaryFile('wb') as master_archive:
        master_archive.write(requests.get(masters_url).content)
        master_archive.flush()
        tar = tarfile.open(master_archive.name)
        tar.extractall(_MASTERS_CDF_PATH)


def update_master_cdf(masters_url: str = "https://spdf.gsfc.nasa.gov/pub/software/cdawlib/0MASTERS/master.tar"):
    last_modified = requests.head(masters_url).headers['last-modified']
    if index.get("cdaweb-inventory", "masters-last-modified", "") != last_modified:
        _clean_master_cdf_folder()
        _download_and_extract_master_cdf(masters_url)
        index.set("cdaweb-inventory", "masters-last-modified", last_modified)
        return True
    return False


def update_xml_catalog(xml_catalog_url: str = "https://spdf.gsfc.nasa.gov/pub/catalogs/all.xml"):
    last_modified = requests.head(xml_catalog_url).headers['last-modified']
    if index.get("cdaweb-inventory", "xml_catalog-last-modified", "") != last_modified:
        _ensure_path_exists(_XML_CATALOG_PATH)
        with open(_XML_CATALOG_PATH, 'w') as f:
            f.write(requests.get(xml_catalog_url).text)
            index.set("cdaweb-inventory", "xml_catalog-last-modified", last_modified)
            return True
    return False


def build_inventory(root: SpeasyIndex = None, xml_catalog_url: str = "https://spdf.gsfc.nasa.gov/pub/catalogs/all.xml",
                    masters_url: str = "https://spdf.gsfc.nasa.gov/pub/software/cdawlib/0MASTERS/master.tar"):
    needs_rebuild = update_xml_catalog(xml_catalog_url)
    needs_rebuild |= update_master_cdf(masters_url)
    if needs_rebuild or not index.contains("cdaweb-inventory", "tree"):
        root = load_xml_catalog(xml_file_path=_XML_CATALOG_PATH, root=root)
        update_tree(root=root, master_cdf_dir=_MASTERS_CDF_PATH)
        index.set("cdaweb-inventory", "tree", to_dict(root))
    else:
        t = from_dict(index.get("cdaweb-inventory", "tree"))
        root.__dict__ = t.__dict__
    return root
