"""Test zha light."""
from unittest.mock import call, patch
from homeassistant.components.light import DOMAIN
from homeassistant.const import STATE_ON, STATE_OFF
from tests.common import mock_coro
from .common import (
    async_init_zigpy_device, make_attribute, make_entity_id,
    async_test_device_join
)

ON = 1
OFF = 0


async def test_light(hass, config_entry, zha_gateway):
    """Test zha light platform."""
    from zigpy.zcl.clusters.general import OnOff, LevelControl
    from zigpy.profiles.zha import DeviceType

    # create zigpy devices
    zigpy_device_on_off = await async_init_zigpy_device(
        hass,
        [OnOff.cluster_id],
        [],
        DeviceType.ON_OFF_LIGHT,
        zha_gateway
    )

    zigpy_device_level = await async_init_zigpy_device(
        hass,
        [OnOff.cluster_id, LevelControl.cluster_id],
        [],
        DeviceType.ON_OFF_LIGHT,
        zha_gateway,
        ieee="00:0d:6f:11:0a:90:69:e7",
        manufacturer="FakeLevelManufacturer",
        model="FakeLevelModel"
    )

    # load up light domain
    await hass.config_entries.async_forward_entry_setup(
        config_entry, DOMAIN)
    await hass.async_block_till_done()

    # on off light
    on_off_device_on_off_cluster = zigpy_device_on_off.endpoints.get(1).on_off
    on_off_entity_id = make_entity_id(DOMAIN, zigpy_device_on_off,
                                      on_off_device_on_off_cluster,
                                      use_suffix=False)

    # dimmable light
    level_device_on_off_cluster = zigpy_device_level.endpoints.get(1).on_off
    level_device_level_cluster = zigpy_device_level.endpoints.get(1).level
    level_entity_id = make_entity_id(DOMAIN, zigpy_device_level,
                                     level_device_on_off_cluster,
                                     use_suffix=False)

    # test that the lights were created and are off
    assert hass.states.get(on_off_entity_id).state == STATE_OFF
    assert hass.states.get(level_entity_id).state == STATE_OFF

    # test turning the lights on and off from the light
    await async_test_on_off_from_light(
        hass, on_off_device_on_off_cluster, on_off_entity_id)

    await async_test_on_off_from_light(
        hass, level_device_on_off_cluster, level_entity_id)

    # test turning the lights on and off from the HA
    await async_test_on_off_from_hass(
        hass, on_off_device_on_off_cluster, on_off_entity_id)

    await async_test_level_on_off_from_hass(
        hass, level_device_on_off_cluster, level_entity_id)

    # test turning the lights on and off from the light
    await async_test_on_from_light(
        hass, level_device_on_off_cluster, level_entity_id)

    # test getting a brightness change from the network
    await async_test_dimmer_from_light(
        hass, level_device_level_cluster, level_entity_id, 150, STATE_ON)

    # test adding a new light to the network and HA
    await async_test_device_join(
        hass, zha_gateway, OnOff.cluster_id,
        DOMAIN, device_type=DeviceType.ON_OFF_LIGHT, expected_state=STATE_OFF)


async def async_test_on_off_from_light(hass, cluster, entity_id):
    """Test on off functionality from the light."""
    # turn on at light
    attr = make_attribute(0, 1)
    cluster.handle_message(False, 1, 0x0a, [[attr]])
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON

    # turn off at light
    attr.value.value = 0
    cluster.handle_message(False, 0, 0x0a, [[attr]])
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF


async def async_test_on_from_light(hass, cluster, entity_id):
    """Test on off functionality from the light."""
    # turn on at light
    attr = make_attribute(0, 1)
    cluster.handle_message(False, 1, 0x0a, [[attr]])
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON


async def async_test_on_off_from_hass(hass, cluster, entity_id):
    """Test on off functionality from hass."""
    from zigpy.zcl.foundation import Status
    with patch(
            'zigpy.zcl.Cluster.request',
            return_value=mock_coro([Status.SUCCESS, Status.SUCCESS])):
        # turn on via UI
        await hass.services.async_call(DOMAIN, 'turn_on', {
            'entity_id': entity_id
        }, blocking=True)
        assert len(cluster.request.mock_calls) == 1
        assert cluster.request.call_args == call(
            False, ON, (), expect_reply=True, manufacturer=None)

    await async_test_off_from_hass(hass, cluster, entity_id)


async def async_test_off_from_hass(hass, cluster, entity_id):
    """Test turning off the light from homeassistant."""
    from zigpy.zcl.foundation import Status
    with patch(
            'zigpy.zcl.Cluster.request',
            return_value=mock_coro([Status.SUCCESS, Status.SUCCESS])):
        # turn off via UI
        await hass.services.async_call(DOMAIN, 'turn_off', {
            'entity_id': entity_id
        }, blocking=True)
        assert len(cluster.request.mock_calls) == 1
        assert cluster.request.call_args == call(
            False, OFF, (), expect_reply=True, manufacturer=None)


async def async_test_level_on_off_from_hass(hass, cluster, entity_id):
    """Test on off functionality from hass."""
    from zigpy import types
    from zigpy.zcl.foundation import Status
    with patch(
            'zigpy.zcl.Cluster.request',
            return_value=mock_coro([Status.SUCCESS, Status.SUCCESS])):
        # turn on via UI
        await hass.services.async_call(DOMAIN, 'turn_on', {
            'entity_id': entity_id
        }, blocking=True)
        assert len(cluster.request.mock_calls) == 1
        assert cluster.request.call_args == call(
            False, 4, (types.uint8_t, types.uint16_t), 255, 5.0,
            expect_reply=True, manufacturer=None)

    await async_test_off_from_hass(hass, cluster, entity_id)


async def async_test_dimmer_from_light(hass, cluster, entity_id,
                                       level, expected_state):
    """Test dimmer functionality from the light."""
    attr = make_attribute(0, level)
    cluster.handle_message(False, 1, 0x0a, [[attr]])
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == expected_state
    # hass uses None for brightness of 0 in state attributes
    if level == 0:
        level = None
    assert hass.states.get(entity_id).attributes.get('brightness') == level
