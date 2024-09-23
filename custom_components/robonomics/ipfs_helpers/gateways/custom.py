from .gateway import Gateway, PinArgs, UnpinArgs
from homeassistant.core import HomeAssistant
import typing as tp
import logging
from robonomicsinterface.utils import web_3_auth
import ipfshttpclient2
from ...const import CONF_IPFS_GATEWAY, DOMAIN, CONF_IPFS_GATEWAY_PORT

_LOGGER = logging.getLogger(__name__)

class Custom(Gateway):

    def __init__(self, hass: HomeAssistant, websession, seed: tp.Optional[str] = None) -> None:
        self.hass = hass
        self.url = self._format_url_for_add_request()
        self.address = self._format_address_for_add_request(self.url)
        self.seed = seed
        super().__init__(self.hass, self.hass.data[DOMAIN][CONF_IPFS_GATEWAY], websession)
    
    async def pin(self, args: PinArgs) -> str:
        file_name: str = args.file_name
        _LOGGER.debug(f"Start adding {file_name} to {self.url}, auth: {bool(self.seed)}")
        try:
            if self.seed is not None:
                self._authorization()
                result = self.hass.async_add_executor_job(self._pin_with_authorization, file_name)
            else:
                result = self.hass.async_add_executor_job(self._pin_without_authorization, file_name)
                ipfs_hash = self._parse_result(result)
                _LOGGER.debug(
                f"File {file_name} was added to {self.address} with cid: {ipfs_hash}"
            )
            return ipfs_hash
        except Exception as e:
            _LOGGER.error(f"Exception in pinning to custom gateway: {e}")
            ipfs_hash = None
            return ipfs_hash
            

    async def unpin(self, args: UnpinArgs) -> None:
        last_file_hash: str = args.last_file_hash
        _LOGGER.debug(f"Start unpinning {last_file_hash} from custom gateway {self.url}")
        try:
            if self.seed is not None:
                self._authorization()
                self.hass.async_add_executor_job(self._unpin_with_authorization, last_file_hash)
            else:
                self.hass.async_add_executor_job(self._unpin_without_authorization, last_file_hash)
        except Exception as e:
            _LOGGER.warning(f"Can't unpin from custom gateway: {e}")
    
    def _authorization(self) -> None:
        try:
            self.usr, self.pwd = web_3_auth(self.seed)
        except Exception as e:
                _LOGGER.warning(f"Can't authorize to custom gateway: {e}.")


    def _format_url_for_add_request(self):
        if "https://" in self.hass.data[DOMAIN][CONF_IPFS_GATEWAY]:
            url = self.hass.data[DOMAIN][CONF_IPFS_GATEWAY][8:]
        if self.hass.data[DOMAIN][CONF_IPFS_GATEWAY][-1] == "/":
            url = self.hass.data[DOMAIN][CONF_IPFS_GATEWAY][:-1]
        return url
    
    def _format_address_for_add_request(self, url: str) -> str:
        return f"/dns4/{url}/tcp/{self.hass.data[DOMAIN][CONF_IPFS_GATEWAY_PORT]}/https"

    def _unpin_with_authorization(self, last_file_hash: str) -> None:
        with ipfshttpclient2.connect(addr=self.address, auth=(self.usr, self.pwd)) as client:
            client.pin.rm(last_file_hash)
            _LOGGER.debug(f"Hash {last_file_hash} was unpinned from {self.address} with authorization")
    
    def _unpin_without_authorization(self, last_file_hash: str) -> None:
        with ipfshttpclient2.connect(addr=self.address) as client:
            client.pin.rm(last_file_hash)
            _LOGGER.debug(f"Hash {last_file_hash} was unpinned from {self.address}")
    
    def _pin_with_authorization(self, filename: str) -> tp.Tuple[str, int]:
        with ipfshttpclient2.connect(addr=self.address, auth=(self.usr, self.pwd)) as client:
            result = client.add(filename)
        return result
    
    def _pin_without_authorization(self, filename: str) -> tp.Tuple[str, int]:
        with ipfshttpclient2.connect(addr=self.address) as client:
            result = client.add(filename)
        return result
    
    def _parse_result(self, result) -> tp.Tuple[str, int]:
        if isinstance(result, list):
                result = result[-1]
        ipfs_hash: tp.Optional[str] = result["Hash"]
        return ipfs_hash