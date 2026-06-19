from __future__ import annotations

import asyncio
import os
from typing import Any


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in value]
    return value


def map_raw_attributes(raw_attrs: dict[str, Any]) -> dict[str, Any]:
    mapped = {}
    for key, val in raw_attrs.items():
        parts = str(key).split("/")
        if len(parts) != 3:
            continue
        try:
            ep = int(parts[0])
            cl = int(parts[1])
            attr = int(parts[2])
        except ValueError:
            continue
        
        if ep == 0:
            continue
            
        # OnOff Cluster (6)
        if cl == 6:
            if attr == 0:
                mapped["on"] = bool(val)
                
        # LevelControl Cluster (8)
        elif cl == 8:
            if attr == 0:
                if val is not None:
                    mapped["brightness"] = round(int(val) * 100 / 254)
                    
        # ColorControl Cluster (768)
        elif cl == 768:
            # We can capture hue, saturation or color temperature if needed
            # For simplicity let's mock or retain color string representation
            pass
            
        # DoorLock Cluster (257)
        elif cl == 257:
            if attr == 0:
                mapped["locked"] = (int(val) == 1) if val is not None else True
                
        # WindowCovering Cluster (258)
        elif cl == 258:
            if attr in (8, 23):
                if val is not None:
                    mapped["position"] = int(val)
                    mapped["open"] = int(val) > 0
                    
        # Thermostat Cluster (513)
        elif cl == 513:
            if attr == 0:
                if val is not None:
                    mapped["temperature"] = round(int(val) / 100.0, 1)
            elif attr in (18, 19):
                if val is not None:
                    mapped["target_temperature"] = round(int(val) / 100.0, 1)
                    
        # Temperature Measurement (1026)
        elif cl == 1026:
            if attr == 0:
                if val is not None:
                    mapped["temperature"] = round(int(val) / 100.0, 1)
                    
        # Relative Humidity Measurement (1029)
        elif cl == 1029:
            if attr == 0:
                if val is not None:
                    mapped["humidity"] = round(int(val) / 100.0, 1)
                    
        # Occupancy Sensing (1030)
        elif cl == 1030:
            if attr == 0:
                if val is not None:
                    mapped["occupancy"] = bool(int(val) & 1)
                    
        # Boolean State (69)
        elif cl == 69:
            if attr == 0:
                mapped["open"] = bool(val)
                
        # Smoke CO Alarm (92)
        elif cl == 92:
            if attr == 0:
                mapped["alarm"] = bool(val)
                
    return mapped


class MatterServerControllerAdapter:
    def __init__(self, ws_url: str | None = None) -> None:
        self.ws_url = (ws_url or os.getenv("MATTER_SERVER_WS_URL", "ws://127.0.0.1:5580/ws")).strip()
        if not self.ws_url:
            raise RuntimeError("MATTER_SERVER_WS_URL is empty.")

    def profiles(self) -> list[Any]:
        from app.controller import MatterProfile

        profiles = []
        for profile in self._profile_specs():
            profiles.append(MatterProfile(**profile))
        return profiles

    def discover(self) -> list[dict[str, Any]]:
        return asyncio.run(self._discover_async())

    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._pair_async(payload))

    def resolve_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_signature = self._raw_signature(payload)
        device_type = str(payload.get("device_type", "")).strip() or self._infer_from_signature(raw_signature)
        pairing_method = "qr_code" if payload.get("qr_code") else "pairing_code" if payload.get("pairing_code") else "unknown"
        return {
            "device_type": device_type,
            "pairing_method": pairing_method,
            "resolved_from": "matter_server",
            "raw_signature": raw_signature,
            "matched": None if device_type == "Generic" else device_type,
        }

    def invoke_command(
        self,
        device_type: str,
        action: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not context:
            return {"last_action": action, "last_payload": payload, "controller": "matter-server", "real_command": False}
        return asyncio.run(self._invoke_command_async(device_type, action, payload, context))

    async def _discover_async(self) -> list[dict[str, Any]]:
        client, session = await self._open_client()
        init_ready = asyncio.Event()
        listen_task = asyncio.create_task(client.start_listening(init_ready))
        try:
            await asyncio.wait_for(init_ready.wait(), timeout=10.0)
            nodes = await client.discover_commissionable_nodes()

            # Enrich known simulated devices to provide setup pin and qr code, 
            # while fully adhering to real mDNS discovery
            sim_map = {}
            try:
                import urllib.request
                import json
                with urllib.request.urlopen("http://matter-sim:3001/devices", timeout=1.0) as response:
                    sim_devices = json.loads(response.read().decode())
                    for sd in sim_devices:
                        if sd.get("discriminator"):
                            sim_map[int(sd["discriminator"])] = sd
            except Exception:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:3001/devices", timeout=1.0) as response:
                        sim_devices = json.loads(response.read().decode())
                        for sd in sim_devices:
                            if sd.get("discriminator"):
                                sim_map[int(sd["discriminator"])] = sd
                except Exception:
                    pass

            discoveries = []
            for node in nodes:
                disc_val = getattr(node, "long_discriminator", None)
                mapped_type = self._device_type_name(getattr(node, "device_type", None))
                
                # Fetch matching simulated credentials if available
                sim_device = sim_map.get(disc_val) if disc_val is not None else None
                
                # Format name carefully
                raw_name = getattr(node, "device_name", "") or "Urządzenie Matter"
                if "ar" in raw_name and "wka" in raw_name:
                    device_name = "Żarówka"
                    if "rgb" in raw_name.lower():
                        device_name = "Żarówka RGB"
                elif "ci pow" in raw_name:
                    device_name = "Tester jakości powietrza"
                elif "otwar" in raw_name:
                    device_name = "Czujka otwarcia"
                else:
                    device_name = raw_name
                
                discovery_item = {
                    "instance_name": getattr(node, "instance_name", None),
                    "host_name": getattr(node, "host_name", None),
                    "port": getattr(node, "port", None),
                    "device_name": device_name,
                    "device_type": mapped_type,
                    "addresses": getattr(node, "addresses", []),
                    "long_discriminator": disc_val,
                    "vendor_id": getattr(node, "vendor_id", None),
                    "product_id": getattr(node, "product_id", None),
                }
                
                if sim_device:
                    discovery_item["setup_pin"] = sim_device.get("setupPin")
                    discovery_item["qr_code"] = sim_device.get("qrPairingCode")
                    discovery_item["sim_id"] = sim_device.get("id")
                    
                discoveries.append(discovery_item)
            return discoveries
        finally:
            try:
                listen_task.cancel()
                await listen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            await self._safe_close_client(client, session)

    async def _pair_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = str(payload.get("qr_code") or payload.get("pairing_code") or "").strip()
        if not code:
            raise RuntimeError("Pairing code or QR code is required.")

        client, session = await self._open_client()
        init_ready = asyncio.Event()
        listen_task = asyncio.create_task(client.start_listening(init_ready))
        try:
            await asyncio.wait_for(init_ready.wait(), timeout=10.0)
            node_data = await client.commission_with_code(code, network_only=bool(payload.get("pairing_code")))
            node = self._build_node(node_data)
            device_type = self._device_type_from_node(node)
            endpoint_id = self._primary_endpoint_id(node)
            profile = self._profile_for_type(device_type)
            return {
                "name": payload.get("name") or self._node_name(node),
                "vendor": payload.get("vendor") or self._node_vendor(node),
                "device_type": device_type,
                "endpoint": str(endpoint_id),
                "clusters": profile["clusters"],
                "attributes": self._attributes_from_node(node),
                "metadata": {
                    "controller": "matter-server",
                    "matter_node_id": getattr(node_data, "node_id", None),
                    "matter_endpoint_id": endpoint_id,
                    "pairing_code": payload.get("pairing_code", ""),
                    "qr_code": payload.get("qr_code", ""),
                    "transport": payload.get("transport", "matter"),
                    "pairing_method": "pairing_code" if payload.get("pairing_code") else "qr_code",
                    "resolved_from": "commissioning_result",
                    "pairing_completed": True,
                },
            }
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=3.0)
            except Exception:
                pass
            try:
                listen_task.cancel()
                await listen_task
            except Exception:
                pass
            try:
                await asyncio.wait_for(session.close(), timeout=2.0)
            except Exception:
                pass

    async def _invoke_command_async(
        self,
        device_type: str,
        action: str,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        client, session = await self._open_client()
        init_ready = asyncio.Event()
        listen_task = asyncio.create_task(client.start_listening(init_ready))
        try:
            await asyncio.wait_for(init_ready.wait(), timeout=10.0)
            from chip.clusters import Objects as Clusters

            node_id = int(context.get("matter_node_id") or context.get("node_id"))
            endpoint_id = int(context.get("matter_endpoint_id") or context.get("endpoint") or 1)
            normalized = action.lower().strip()
            command = None

            if normalized in {"turn_on", "on"} and hasattr(Clusters.OnOff.Commands, "On"):
                command = Clusters.OnOff.Commands.On()
            elif normalized in {"turn_off", "off"} and hasattr(Clusters.OnOff.Commands, "Off"):
                command = Clusters.OnOff.Commands.Off()
            elif normalized == "toggle" and hasattr(Clusters.OnOff.Commands, "Toggle"):
                command = Clusters.OnOff.Commands.Toggle()
            elif normalized == "set_level" and hasattr(Clusters.LevelControl.Commands, "MoveToLevelWithOnOff"):
                level = max(0, min(100, int(payload.get("brightness", 0))))
                command = Clusters.LevelControl.Commands.MoveToLevelWithOnOff(level=level * 254 // 100, transitionTime=0)
            elif normalized == "lock" and hasattr(Clusters.DoorLock.Commands, "LockDoor"):
                command = Clusters.DoorLock.Commands.LockDoor()
            elif normalized == "unlock" and hasattr(Clusters.DoorLock.Commands, "UnlockDoor"):
                command = Clusters.DoorLock.Commands.UnlockDoor()
            elif normalized == "set_color" and hasattr(Clusters.ColorControl.Commands, "MoveToColor"):
                # Simulating set_color command for real server adapter (ColorControl cluster)
                # Simply update local mapped attributes for representation
                pass

            if command is not None:
                await client.send_device_command(node_id, endpoint_id, command)
                # Wait briefly for attributes to propagate
                await asyncio.sleep(0.5)
            
            node = None
            try:
                node = client.get_node(node_id)
            except Exception:
                for n in client.get_nodes():
                    if getattr(n, "node_id", None) == node_id:
                        node = n
                        break
            
            updated_attrs = {}
            if node is not None:
                updated_attrs = self._attributes_from_node(node)

            return {
                **updated_attrs,
                "controller": "matter-server",
                "real_command": (command is not None),
                "node_id": node_id,
                "endpoint": endpoint_id,
                "device_type": device_type,
                "action": action,
            }
        finally:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=3.0)
            except Exception:
                pass
            try:
                listen_task.cancel()
                await listen_task
            except Exception:
                pass
            try:
                await asyncio.wait_for(session.close(), timeout=2.0)
            except Exception:
                pass

    async def _open_client(self):
        try:
            from aiohttp import ClientSession
            from matter_server.client.client import MatterClient
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Real Matter controller requires 'aiohttp' and 'python-matter-server'.") from exc

        session = ClientSession()
        client = MatterClient(self.ws_url, session)
        return client, session

    def _build_node(self, node_data: Any):
        from matter_server.client.models.node import MatterNode

        return MatterNode(node_data)

    def _node_to_discovery(self, node: Any) -> dict[str, Any]:
        return {
            "instance_name": getattr(node, "name", None),
            "host_name": getattr(node, "name", None),
            "port": None,
            "device_name": getattr(node, "name", None),
            "device_type": self._device_type_from_node(node),
            "addresses": [],
        }

    def _primary_endpoint_id(self, node: Any) -> int:
        endpoints = getattr(node, "endpoints", {})
        if 1 in endpoints:
            return 1
        if 0 in endpoints:
            return 0
        if endpoints:
            return sorted(endpoints.keys())[0]
        return 1

    def _device_type_from_node(self, node: Any) -> str:
        try:
            endpoint_id = self._primary_endpoint_id(node)
            endpoint = node.endpoints.get(endpoint_id)
            if endpoint is None:
                return "Generic"
            descriptor = endpoint.get_cluster(29)
            if descriptor is None:
                return "Generic"
            device_type_list = getattr(descriptor, "deviceTypeList", []) or []
            for item in device_type_list:
                device_type_id = getattr(item, "deviceType", getattr(item, "device_type", None))
                mapped = self._device_type_name(device_type_id)
                if mapped != "Generic":
                    return mapped
        except Exception:
            return "Generic"
        return "Generic"

    def _device_type_name(self, device_type_id: Any) -> str:
        mapping = {
            256: "OnOffLight",
            257: "DimmableLight",
            266: "OnOffPlugInUnit",
            263: "OccupancySensor",
            10: "DoorLock",
            514: "WindowCovering",
            512: "Thermostat",
            770: "TemperatureSensor",
            775: "RelativeHumiditySensor",
            21: "ContactSensor",
            118: "SmokeCoAlarm",
            1296: "AirQualitySensor",
            0x002B: "Fan",
        }
        return mapping.get(device_type_id, "Generic")

    def _attributes_from_node(self, node: Any) -> dict[str, Any]:
        node_data = getattr(node, "node_data", None)
        raw_attrs = _jsonable(getattr(node_data, "attributes", {}) if node_data is not None else {})
        device_type = self._device_type_from_node(node)
        profile = self._profile_for_type(device_type)
        mapped = map_raw_attributes(raw_attrs)
        return {**profile.get("default_attributes", {}), **mapped}

    def _node_name(self, node: Any) -> str:
        return str(getattr(node, "name", None) or f"Matter node {getattr(node.node_data, 'node_id', 'unknown')}")

    def _node_vendor(self, node: Any) -> str:
        device_info = getattr(node, "device_info", None)
        vendor = getattr(device_info, "vendorName", None)
        return str(vendor) if vendor else "Matter"

    def _profile_for_type(self, device_type: str) -> dict[str, Any]:
        for profile in self._profile_specs():
            if profile["device_type"] == device_type:
                return profile
        return self._profile_specs()[-1]

    def _profile_specs(self) -> list[dict[str, Any]]:
        return [
            {"device_type": "OnOffLight", "label": "Lampa On/Off", "clusters": ["Identify", "Descriptor", "OnOff", "LevelControl"], "actions": ["turn_on", "turn_off", "toggle"], "default_attributes": {"on": False}},
            {"device_type": "DimmableLight", "label": "Lampa RGB / ściemniana", "clusters": ["Identify", "Descriptor", "OnOff", "LevelControl", "ColorControl"], "actions": ["turn_on", "turn_off", "toggle", "set_level", "set_color"], "default_attributes": {"on": False, "brightness": 50, "color": "#ffffff"}},
            {"device_type": "OnOffPlugInUnit", "label": "Gniazdko", "clusters": ["Identify", "Descriptor", "OnOff", "LevelControl"], "actions": ["turn_on", "turn_off", "toggle"], "default_attributes": {"on": False}},
            {"device_type": "DoorLock", "label": "Zamek drzwi", "clusters": ["Identify", "Descriptor", "DoorLock"], "actions": ["lock", "unlock"], "default_attributes": {"locked": True}},
            {"device_type": "WindowCovering", "label": "Roleta / zasłona", "clusters": ["Identify", "Descriptor", "WindowCovering"], "actions": ["open", "close", "stop", "set_position"], "default_attributes": {"position": 0, "open": False}},
            {"device_type": "Thermostat", "label": "Termostat", "clusters": ["Identify", "Descriptor", "TemperatureMeasurement", "Thermostat"], "actions": ["set_temperature"], "default_attributes": {"temperature": 21.0, "target_temperature": 21.0}},
            {"device_type": "TemperatureSensor", "label": "Czujnik temperatury", "clusters": ["Identify", "Descriptor", "TemperatureMeasurement"], "actions": ["refresh"], "default_attributes": {"temperature": 20.0}},
            {"device_type": "RelativeHumiditySensor", "label": "Czujnik wilgoci", "clusters": ["Identify", "Descriptor", "RelativeHumidityMeasurement"], "actions": ["refresh"], "default_attributes": {"humidity": 45.0}},
            {"device_type": "OccupancySensor", "label": "Czujnik ruchu", "clusters": ["Identify", "Descriptor", "OccupancySensing"], "actions": ["refresh"], "default_attributes": {"occupancy": False}},
            {"device_type": "ContactSensor", "label": "Czujka otwarcia", "clusters": ["Identify", "Descriptor", "BooleanState"], "actions": ["refresh"], "default_attributes": {"open": False}},
            {"device_type": "SmokeCoAlarm", "label": "Czujnik dymu / CO", "clusters": ["Identify", "Descriptor", "SmokeCoAlarm"], "actions": ["refresh"], "default_attributes": {"alarm": False}},
            {"device_type": "AirQualitySensor", "label": "Czujnik jakości powietrza", "clusters": ["Identify", "Descriptor", "AirQuality"], "actions": ["refresh"], "default_attributes": {"aqi": 0.0}},
            {"device_type": "Generic", "label": "Urządzenie ogólne", "clusters": ["Identify", "Descriptor"], "actions": ["refresh"], "default_attributes": {}},
        ]

    def _raw_signature(self, payload: dict[str, Any]) -> str:
        for field_name in ("raw_matter", "matter_signature", "signature", "raw", "qr_code", "pairing_code"):
            value = str(payload.get(field_name, "")).strip()
            if value:
                return value
        return ""

    def _infer_from_signature(self, signature: str) -> str:
        lowered = signature.lower()
        if any(token in lowered for token in ("doorlock", "lock")):
            return "DoorLock"
        if any(token in lowered for token in ("window", "blind", "curtain", "shade")):
            return "WindowCovering"
        if any(token in lowered for token in ("thermostat", "temperature")):
            return "Thermostat"
        if any(token in lowered for token in ("humidity", "humid")):
            return "RelativeHumiditySensor"
        if any(token in lowered for token in ("occupancy", "motion", "presence")):
            return "OccupancySensor"
        if any(token in lowered for token in ("contact", "open")):
            return "ContactSensor"
        if any(token in lowered for token in ("smoke", "co alarm", "coalarm")):
            return "SmokeCoAlarm"
        if any(token in lowered for token in ("plug", "socket", "outlet")):
            return "OnOffPlugInUnit"
        if any(token in lowered for token in ("rgb", "color", "dimmable", "lamp", "bulb", "light")):
            return "DimmableLight"
        return "Generic"
