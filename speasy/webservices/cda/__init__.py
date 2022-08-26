# -*- coding: utf-8 -*-

"""CDA_Webservice package for Space Physics WebServices Client."""

__author__ = """Alexis Jeandet"""
__email__ = 'alexis.jeandet@member.fsf.org'
__version__ = '0.1.0'

from typing import Optional, Tuple
from datetime import datetime, timedelta
from speasy.core.cache import UnversionedProviderCache, CACHE_ALLOWED_KWARGS, \
    _cache  # _cache is used for tests (hack...)
from speasy.products.variable import SpeasyVariable
from speasy.core import http, AllowedKwargs
from speasy.core.proxy import Proxyfiable, GetProduct, PROXY_ALLOWED_KWARGS
from speasy.core.cdf import load_variable
from speasy.core.inventory.indexes import ParameterIndex, SpeasyIndex, DatasetIndex
from speasy.core.dataprovider import DataProvider
from speasy.core.datetime_range import DateTimeRange
from urllib.request import urlopen
import logging

log = logging.getLogger(__name__)


class CdaWebException(BaseException):
    def __init__(self, text):
        super(CdaWebException, self).__init__(text)


def _read_cdf(url: str, variable: str) -> SpeasyVariable:
    with urlopen(url) as remote_cdf:
        return load_variable(buffer=remote_cdf.read(), variable=variable)


def get_parameter_args(start_time: datetime, stop_time: datetime, product: str, **kwargs):
    return {'path': f"cdaweb/{product}", 'start_time': f'{start_time.isoformat()}',
            'stop_time': f'{stop_time.isoformat()}'}


def to_dataset_and_variable(index_or_str: ParameterIndex or str) -> Tuple[str, str]:
    if type(index_or_str) is str:
        parts = index_or_str.split('/')
    elif type(index_or_str) is ParameterIndex:
        parts = index_or_str.product.split('/')
    else:
        raise TypeError(f"given parameter {index_or_str} of type {type(index_or_str)} is not a compatible index")
    assert len(parts) == 2
    return parts[0], parts[1]


class CDA_Webservice(DataProvider):
    def __init__(self):
        self.__url = "https://cdaweb.gsfc.nasa.gov/WS/cdasr/1"
        DataProvider.__init__(self, provider_name='cda', provider_alt_names=['cdaweb'])

    def build_inventory(self, root: SpeasyIndex):
        from ._inventory_builder import build_inventory
        root = build_inventory(root=root)
        return root

    def parameter_range(self, parameter_id: str or ParameterIndex) -> Optional[DateTimeRange]:
        """Get product time range.

        Parameters
        ----------
        parameter_id: str or ParameterIndex
            parameter id

        Returns
        -------
        Optional[DateTimeRange]
            Data time range

        Examples
        --------

        >>> import speasy as spz
        >>> spz.cda.parameter_range("AC_H0_MFI/BGSEc")
        <DateTimeRange: 1997-09-02T00:00:12+00:00 -> ...>

        """
        return self._parameter_range(parameter_id)

    def dataset_range(self, dataset_id: str or DatasetIndex) -> Optional[DateTimeRange]:
        """Get product time range.

        Parameters
        ----------
        dataset_id: str or DatasetIndex
            parameter id

        Returns
        -------
        Optional[DateTimeRange]
            Data time range

        Examples
        --------

        >>> import speasy as spz
        >>> spz.cda.dataset_range("AC_H0_MFI")
        <DateTimeRange: 1997-09-02T00:00:12+00:00 -> ...>

        """
        return self._dataset_range(dataset_id)

    def _dl_variable(self,
                     dataset: str, variable: str,
                     start_time: datetime, stop_time: datetime, if_newer_than: datetime or None = None) -> Optional[
        SpeasyVariable]:

        start_time, stop_time = start_time.strftime('%Y%m%dT%H%M%SZ'), stop_time.strftime('%Y%m%dT%H%M%SZ')
        fmt = "cdf"
        url = f"{self.__url}/dataviews/sp_phys/datasets/{dataset}/data/{start_time},{stop_time}/{variable}?format={fmt}"
        headers = {"Accept": "application/json"}
        if if_newer_than is not None:
            headers["If-Modified-Since"] = if_newer_than.ctime()
        resp = http.get(url, headers=headers)
        log.debug(resp.url)
        if resp.status_code == 200 and 'FileDescription' in resp.json():
            return _read_cdf(resp.json()['FileDescription'][0]['Name'], variable)
        elif not resp.ok:
            if resp.status_code == 404 and "No data available" in resp.json().get('Message', [""])[0]:
                log.warning(f"Got 404 'No data available' from CDAWeb with {url}")
                return None
            raise CdaWebException(f'Failed to get data with request: {url}, got {resp.status_code} HTTP response')
        else:
            return None

    @AllowedKwargs(
        PROXY_ALLOWED_KWARGS + CACHE_ALLOWED_KWARGS + ['product', 'start_time', 'stop_time', 'if_newer_than'])
    @UnversionedProviderCache(prefix="cda", fragment_hours=lambda x: 12, cache_retention=timedelta(days=7))
    @Proxyfiable(GetProduct, get_parameter_args)
    def get_data(self, product, start_time: datetime, stop_time: datetime, if_newer_than: datetime or None = None):
        p_range = self.parameter_range(product)
        if not p_range.intersect(DateTimeRange(start_time, stop_time)):
            log.warning(f"You are requesting {product} outside of its definition range {p_range}")
            return None

        dataset, variable = to_dataset_and_variable(product)
        return self._dl_variable(start_time=start_time, stop_time=stop_time, dataset=dataset,
                                 variable=variable, if_newer_than=if_newer_than)

    def get_variable(self, dataset: str, variable: str, start_time: datetime or str, stop_time: datetime or str,
                     **kwargs) -> \
        Optional[SpeasyVariable]:
        return self.get_data(f"{dataset}/{variable}", start_time, stop_time, **kwargs)
