import requests
from astroquery.utils.tap.core import TapPlus
from .indexes import CSADatasetIndex, CSAParameterIndex, to_dataset_and_variable
from typing import Optional
from datetime import datetime
from speasy.core.cache import Cacheable, CACHE_ALLOWED_KWARGS, _cache  # _cache is used for tests (hack...)
from speasy.products.variable import SpeasyVariable
from speasy.core import http, AllowedKwargs
from speasy.core.proxy import Proxyfiable, GetProduct, PROXY_ALLOWED_KWARGS
from speasy.core.cdf import load_variable
from ...inventory import flat_inventories
from urllib.request import urlopen
from tempfile import NamedTemporaryFile
from tempfile import TemporaryDirectory
import tarfile
import logging

log = logging.getLogger(__name__)


def build_inventory(tapurl="https://csa.esac.esa.int/csa-sl-tap/tap/"):
    CSA = TapPlus(url=tapurl)
    datasets = CSA.launch_job_async("SELECT * FROM csa.v_dataset WHERE is_cef='true'").get_results()
    colnames = datasets.colnames
    for d in datasets:
        CSADatasetIndex(**{cname: d[cname] for cname in colnames})

    parameters = CSA.launch_job_async("SELECT * FROM csa.v_parameter WHERE data_type='Data'").get_results()
    colnames = parameters.colnames
    for c in parameters:
        if c["dataset_id"] in flat_inventories.csa.datasets:
            CSAParameterIndex(**{cname: c[cname] for cname in colnames})


def _read_cdf(req: requests.Response, variable: str) -> SpeasyVariable:
    with NamedTemporaryFile('wb') as tmp_tar:
        tmp_tar.write(req.content)
        tmp_tar.flush()
        with tarfile.open(tmp_tar.name) as tar:
            tarname = tar.getnames()
            with TemporaryDirectory() as tmp_dir:
                tar.extractall(tmp_dir)
                return load_variable(file=f"{tmp_dir}/{tarname[0]}", variable=variable)


def get_parameter_args(start_time: datetime, stop_time: datetime, product: str, **kwargs):
    return {'path': f"cdaweb/{product}", 'start_time': f'{start_time.isoformat()}',
            'stop_time': f'{stop_time.isoformat()}'}


class CSA_Webservice:
    def __init__(self):
        self.__url = "https://csa.esac.esa.int/csa-sl-tap/data"

    def _dl_variable(self,
                     dataset: str, variable: str,
                     start_time: datetime, stop_time: datetime) -> Optional[SpeasyVariable]:

        # https://csa.esac.esa.int/csa-sl-tap/data?RETRIEVAL_TYPE=product&&DATASET_ID=C3_CP_PEA_LERL_DEFlux&START_DATE=2001-06-10T22:12:14Z&END_DATE=2001-06-11T06:12:14Z&DELIVERY_FORMAT=CDF_ISTP&DELIVERY_INTERVAL=all

        resp = http.get(self.__url, params={
            "RETRIEVAL_TYPE": "product",
            "DATASET_ID": dataset,
            "START_DATE": start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "END_DATE": stop_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "DELIVERY_FORMAT": "CDF_ISTP",
            "DELIVERY_INTERVAL": "all"
        })
        if resp.status_code != 200:
            raise RuntimeError(f'Failed to get data with request: {resp.url}, got {resp.status_code} HTTP response')
        if not resp.ok:
            return None
        return _read_cdf(resp, variable)

    @AllowedKwargs(PROXY_ALLOWED_KWARGS + CACHE_ALLOWED_KWARGS + ['product', 'start_time', 'stop_time'])
    @Cacheable(prefix="csa", fragment_hours=lambda x: 12)
    @Proxyfiable(GetProduct, get_parameter_args)
    def get_data(self, product, start_time: datetime, stop_time: datetime):
        dataset, variable = to_dataset_and_variable(product)
        return self._dl_variable(start_time=start_time, stop_time=stop_time, dataset=dataset,
                                 variable=variable)

    def get_variable(self, dataset: str, variable: str, start_time: datetime or str, stop_time: datetime or str,
                     **kwargs) -> \
        Optional[SpeasyVariable]:
        return self.get_data(f"{dataset}/{variable}", start_time, stop_time, **kwargs)
