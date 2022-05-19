from __future__ import annotations
from pickle import FALSE
from platform import platform

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.person import async_create_person
from homeassistant.const import TEMP_CELSIUS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.core import StateMachine as sm
from homeassistant.helpers.template import AllStates
from homeassistant.auth import auth_manager_from_config, auth_store, models

from homeassistant.helpers import device_registry as dr

from substrateinterface import SubstrateInterface, Keypair, KeypairType
from substrateinterface.exceptions import SubstrateRequestException
import asyncio
import nacl.secret
from homeassistant import *
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, StateMachine
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import *
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
import logging
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from robonomicsinterface import RobonomicsInterface, Subscriber, SubEvent
import functools
from tenacity import retry, stop_after_attempt, wait_fixed
from substrateinterface.utils.ss58 import is_valid_ss58_address

DATALOG_SWITCH = False
CONTROL_SWITCH = False
ATTR_NAME = "name"
DEFAULT_NAME = "World"

ATTR_ENTITY = "entity_id"
DEFAULT_ENTITY = "sun.sun"
_LOGGER = logging.getLogger(__name__)
datalog_data = ''

from .const import CONF_REPOS, DOMAIN
from .utils import encrypt_message, str2bool

import random, string

def to_thread(func: typing.Callable) -> typing.Coroutine:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper

async def call_service(hass, platform, name, params):
    try:
        await hass.services.async_call(platform, name, params)
        print(f"service worked")
    except Exception as e:
        print(f"Call service exception: {e}")

def generate_pass(length):
   letters = string.ascii_lowercase
   return ''.join(random.choice(letters) for i in range(length))

async def async_setup_entry(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
) -> bool:
    _LOGGER.debug("here from init")
    """Set up platform from a ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    conf = config_entry.data
    mnemonic = conf['seed']
    _LOGGER.debug(mnemonic)
    _LOGGER.debug(f"Robonomics user control starting set up")
    # print(f"Data: {config_entry}")

    def fail_send_datalog(retry_state):
        print(f"Failed send datalog, retry_state: {retry_state}")

    @to_thread
    @retry(stop=stop_after_attempt(5), wait=wait_fixed(5), retry_error_callback=fail_send_datalog)
    def send_datalog(data: str):
        interface = RobonomicsInterface(mnemonic)
        try:
            _LOGGER.debug(f"Start creating datalog")
            receipt = interface.record_datalog(data)
            _LOGGER.debug(f"Datalog created with hash: {receipt}")
        except Exception as e:
            _LOGGER.debug(f"send datalog exception: {e}")
            raise e

    @to_thread
    def subscribe(hass, callback):
        try:
            interface = RobonomicsInterface(seed=mnemonic)
            subscriber = Subscriber(interface, SubEvent.NewDevices, callback, interface.define_address())
        except Exception as e:
            _LOGGER.debug(f"subscribe exception {e}")

    async def get_provider():
        hass.auth = await auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
        provider = hass.auth.auth_providers[0]
        await provider.async_initialize()
        return provider

    async def create_user(provider, username: str, password: str) -> None:
        """
        Create user in Home Assistant
        """
        try:
            _LOGGER.debug(f"Start creating user: {username}")
            provider.data.add_auth(username, password)
            creds = models.Credentials(auth_provider_type='homeassistant', 
                                    auth_provider_id=None, 
                                    data={'username': username}, 
                                    id=username, is_new=True)
            
            resp = await hass.auth.async_get_or_create_user(creds)
            # new_user = await hass.auth.async_create_user(username, ["system-users"])
            # await async_create_person(hass, username, user_id=new_user.id)
            _LOGGER.debug(f"User was created: {username}, password: {password}")
        except Exception as e:
            _LOGGER.debug(f"Exception in create user: {e}")

    async def delete_user(provider, username: str) -> None:
        """
        Delete user from Home Assistant
        """
        try:
            _LOGGER.debug(f"Start deleting user {username}")
            provider.data.async_remove_auth(username)
            users = await hass.auth.async_get_users()
            for user in users:
                if user.name == username:
                    await hass.auth.async_remove_user(user)
            # await storage_collection.async_update_item(
            #         person[CONF_ID], {CONF_USER_ID: None}
            #     )
            _LOGGER.debug(f"User was deleted: {user.name}")
        except Exception as e:
            _LOGGER.debug(f"Exception in delete user: {e}")

    async def manage_users(data) -> None:
        """
        Compare users and data from transaction decide what users must be created or deleted
        """
        provider = await get_provider()

        # users = await hass.auth.async_get_users()
        users = provider.data.users
        print(f"Begining users: {users}")
        usernames_hass = []
        for user in users:
            try:
                username = user['username']
                # username = user.credentials[0].data['username']
                # print(username)
                if len(username) == 48 and username[0] == "4":
                    # print(f"here {username}")
                    usernames_hass.append(username)
                    # print(usernames_hass)
            except Exception as e:
                _LOGGER.debug(f"Exception from manage users: {e}")
        _LOGGER.debug(f"Users before: {provider.data.users}")
        devices = data[1]
        devices = [device.lower() for device in devices]
        # _LOGGER.debug(f"Users {provider.data.users}")
        print(f"Devices: {set(devices)}")
        print(f"Users: {set(usernames_hass)}")
        users_to_add = list(set(devices) - set(usernames_hass))
        _LOGGER.debug(f"New users will be created: {users_to_add}")
        users_to_delete = list(set(usernames_hass) - set(devices))
        _LOGGER.debug(f"Following users will be deleted: {users_to_delete}")

        sender_kp = Keypair.create_from_mnemonic(mnemonic, crypto_type=KeypairType.ED25519)
        for user in users_to_add:
            password = generate_pass(6)
            await create_user(provider, user, password)
            for address in data[1]:
                if address.lower() == user:
                    try:
                        rec_kp = Keypair(ss58_address=address, crypto_type=KeypairType.ED25519)
                        encrypted = encrypt_message(f"Username: {address}, password: {password}", sender_kp, rec_kp.public_key)
                        await send_datalog(encrypted)
                    except Exception as e:
                        print(f"create keypair exception: {e}")
        for user in users_to_delete:
            await delete_user(provider, user)

        if len(users_to_add) > 0 or len(users_to_delete) > 0:
            await provider.data.async_save()
            _LOGGER.debug(f"Finishing user managment, user list: {provider.data.users}")
            _LOGGER.debug("Restarting...")
            await hass.services.async_call("homeassistant", "restart")

    def callback(data) -> None:
        _LOGGER.debug(f"Got NewDevices event: {data}")
        hass.async_create_task(manage_users(data))

    try:
        hass.async_create_task(subscribe(hass, callback))
        _LOGGER.debug("Listener is up")
    except Exception as e:
        _LOGGER.debug(f"Async_setup exception: {e}")

    hass.states.async_set(f"{DOMAIN}.state", "Online")
    _LOGGER.debug(f"Robonomics user control successfuly set up")
    return True

async def async_setup(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:

    return True