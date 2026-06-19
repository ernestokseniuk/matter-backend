from __future__ import annotations

import asyncio
import json
import importlib
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from typing import Any, Protocol

from .pairing_jobs import append_job_log, update_job


@dataclass(frozen=True)
class MatterProfile:
    device_type: str
    label: str
    clusters: list[str]
    actions: list[str]
    default_attributes: dict[str, Any]


class MatterController(Protocol):
    def profiles(self) -> list[MatterProfile]:
        ...

    def discover(self) -> list[dict[str, Any]]:
        ...

    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def resolve_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def invoke_command(
        self,
        device_type: str,
        action: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class MockMatterController:
    def __init__(self) -> None:
        self._profiles = [
            MatterProfile(
                device_type="OnOffLight",
                label="Lampa On/Off",
                clusters=["Identify", "OnOff"],
                actions=["turn_on", "turn_off", "toggle"],
                default_attributes={"on": False},
            ),
            MatterProfile(
                device_type="DimmableLight",
                label="Lampa RGB / ściemniana",
                clusters=["Identify", "OnOff", "LevelControl", "ColorControl"],
                actions=["turn_on", "turn_off", "toggle", "set_level", "set_color"],
                default_attributes={"on": False, "brightness": 50, "color": "#ffffff"},
            ),
            MatterProfile(
                device_type="Switch",
                label="Przełącznik",
                clusters=["Identify", "OnOff"],
                actions=["turn_on", "turn_off", "toggle"],
                default_attributes={"on": False},
            ),
            MatterProfile(
                device_type="OnOffPlugInUnit",
                label="Gniazdko",
                clusters=["Identify", "OnOff", "ElectricalMeasurement"],
                actions=["turn_on", "turn_off", "toggle"],
                default_attributes={"on": False},
            ),
            MatterProfile(
                device_type="DoorLock",
                label="Zamek drzwi",
                clusters=["Identify", "DoorLock"],
                actions=["lock", "unlock"],
                default_attributes={"locked": True},
            ),
            MatterProfile(
                device_type="WindowCovering",
                label="Roleta / zasłona",
                clusters=["Identify", "WindowCovering"],
                actions=["open", "close", "stop", "set_position"],
                default_attributes={"position": 0, "open": False},
            ),
            MatterProfile(
                device_type="Thermostat",
                label="Termostat",
                clusters=["Identify", "TemperatureMeasurement", "Thermostat"],
                actions=["set_temperature"],
                default_attributes={"temperature": 21.0, "target_temperature": 21.0},
            ),
            MatterProfile(
                device_type="TemperatureSensor",
                label="Czujnik temperatury",
                clusters=["Identify", "TemperatureMeasurement"],
                actions=["refresh"],
                default_attributes={"temperature": 20.0},
            ),
            MatterProfile(
                device_type="RelativeHumiditySensor",
                label="Czujnik wilgoci",
                clusters=["Identify", "RelativeHumidityMeasurement"],
                actions=["refresh"],
                default_attributes={"humidity": 45.0},
            ),
            MatterProfile(
                device_type="AirQualitySensor",
                label="Tester jakości powietrza",
                clusters=["Identify", "AirQuality", "OccupancySensor"],
                actions=["refresh"],
                default_attributes={"aqi": 0.0},
            ),
            MatterProfile(
                device_type="ContactSensor",
                label="Czujka otwarcia",
                clusters=["Identify", "ContactSensor"],
                actions=["refresh"],
                default_attributes={"open": False},
            ),
            MatterProfile(
                device_type="OccupancySensor",
                label="Czujnik ruchu",
                clusters=["Identify", "OccupancySensor"],
                actions=["refresh"],
                default_attributes={"occupancy": False},
            ),
            MatterProfile(
                device_type="SmokeCoAlarm",
                label="Czujnik dymu / CO",
                clusters=["Identify", "SmokeCoAlarm"],
                actions=["refresh"],
                default_attributes={"alarm": False},
            ),
            MatterProfile(
                device_type="Generic",
                label="Urządzenie ogólne",
                clusters=["Identify"],
                actions=["refresh"],
                default_attributes={},
            ),
        ]

    def profiles(self) -> list[MatterProfile]:
        return list(self._profiles)

    def discover(self) -> list[dict[str, Any]]:
        return [
            {
                "instance_name": "94E9B6781210AB70",
                "host_name": "4236CD81345E0000",
                "port": 5540,
                "device_name": "Żarówka",
                "device_type": "OnOffLight",
                "addresses": ["127.0.0.1"],
                "long_discriminator": 2391,
                "vendor_id": 0,
                "product_id": 0,
                "setup_pin": "77410680",
                "qr_code": "MT:Y.K90G-K17MI6436O10",
                "sim_id": "light-onoff-01"
            },
            {
                "instance_name": "3742F98D7EEEA6BE",
                "host_name": "4236CD81345E0000",
                "port": 5552,
                "device_name": "Gniazdko",
                "device_type": "OnOffPlugInUnit",
                "addresses": ["127.0.0.1"],
                "long_discriminator": 2995,
                "vendor_id": 0,
                "product_id": 0,
                "setup_pin": "33213859",
                "qr_code": "MT:Y.K90MPP03CDHX4PQ00",
                "sim_id": "outlet-13"
            },
            {
                "instance_name": "746A041B983E586B",
                "host_name": "4236CD81345E0000",
                "port": 5559,
                "device_name": "Termostat",
                "device_type": "Thermostat",
                "addresses": ["127.0.0.1"],
                "long_discriminator": 622,
                "vendor_id": 0,
                "product_id": 0,
                "setup_pin": "83592001",
                "qr_code": "MT:Y.K908OC16NFT705T10",
                "sim_id": "thermostat-20"
            }
        ]

    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("_pair_job_id") or "").strip()
        if job_id:
            import time
            update_job(job_id, status="running", stage="connecting", message="Inicjowanie parowania w trybie Mock.")
            append_job_log(job_id, "Wyszukiwanie urządzenia w sieci lokalnej przy użyciu mDNS...")
            time.sleep(1.0)
            update_job(job_id, status="running", stage="PASE", message="Ustanawianie bezpiecznej sesji PASE.")
            append_job_log(job_id, "Wymiana kluczy kryptograficznych (PASE Handshake). Sprawdzanie kodu parowania.")
            time.sleep(1.2)
            update_job(job_id, status="running", stage="commissioning", message="Weryfikacja certyfikatów urządzenia.")
            append_job_log(job_id, "Odczytywanie i walidacja Device Attestation Certificate (DAC) oraz Product ID...")
            time.sleep(1.0)
            update_job(job_id, status="running", stage="signing", message="Generowanie poświadczeń operacyjnych.")
            append_job_log(job_id, "Wysyłanie żądania podpisania certyfikatu (CSR). Generowanie Node Operational Certificate (NOC)...")
            time.sleep(0.8)
            update_job(job_id, status="running", stage="reading_node", message="Odczytywanie punktów końcowych urządzenia.")
            append_job_log(job_id, "Skanowanie punktów końcowych (endpoints) i deskryptorów klastrów...")
            time.sleep(1.0)
            update_job(job_id, status="running", stage="finalizing", message="Zapisywanie sparowanego urządzenia.")
            append_job_log(job_id, "Urządzenie pomyślnie komisjonowane jako sparowany węzeł Matter.")

        resolved = self.resolve_pairing(payload)
        profile = self.profile_for(resolved["device_type"])
        return {
            "name": payload["name"],
            "vendor": payload.get("vendor", "Unknown Vendor"),
            "device_type": resolved["device_type"],
            "endpoint": payload.get("endpoint", "1"),
            "clusters": payload.get("clusters", profile.clusters),
            "attributes": {**profile.default_attributes, **payload.get("attributes", {})},
            "metadata": {
                "pairing_code": payload.get("pairing_code", "manual"),
                "qr_code": payload.get("qr_code", ""),
                "transport": payload.get("transport", "matter"),
                "matter_standard": "1.3",
                "controller": "mock",
                "pairing_method": resolved["pairing_method"],
                "resolved_from": resolved["resolved_from"],
                "pairing_pending": False,
            },
        }

    def resolve_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        qr_code = str(payload.get("qr_code", "")).strip()
        pairing_code = str(payload.get("pairing_code", "")).strip()
        clusters = self._resolve_clusters(payload)
        raw_signature = self._resolve_raw_signature(payload)
        device_type = str(payload.get("device_type", "")).strip()

        # If device_type explicitly provided by caller, trust it.
        if device_type:
            return {
                "device_type": device_type,
                "pairing_method": "manual",
                "resolved_from": "device_type",
                "raw_signature": raw_signature,
                "clusters": clusters,
                "tokens": self._extract_matter_tokens(raw_signature) if raw_signature else [],
                "matched": "device_type",
            }

        if clusters:
            inferred_debug = self._infer_from_clusters_debug(clusters)
            if inferred_debug["device_type"] != "Generic":
                return {
                    "device_type": inferred_debug["device_type"],
                    "pairing_method": "cluster",
                    "resolved_from": "clusters",
                    "raw_signature": raw_signature,
                    "clusters": clusters,
                    "tokens": inferred_debug.get("tokens", []),
                    "matched": inferred_debug.get("matched"),
                }

        if qr_code or pairing_code:
            inferred = self._infer_from_signature(qr_code or pairing_code)
            return {
                "device_type": inferred,
                "pairing_method": "qr" if qr_code else "pairing_code",
                "resolved_from": "qr_resolution" if qr_code else "pairing_code_resolution",
                "raw_signature": raw_signature or qr_code or pairing_code,
                "clusters": clusters or self.profile_for(inferred).clusters,
                "tokens": self._extract_matter_tokens(raw_signature or qr_code or pairing_code),
                "matched": inferred if inferred != "Generic" else None,
            }

        return {
            "device_type": "Generic",
            "pairing_method": "unknown",
            "resolved_from": "clusters_required",
            "raw_signature": raw_signature or qr_code or pairing_code,
            "clusters": clusters,
            "tokens": [],
            "matched": None,
        }

    def invoke_command(
        self,
        device_type: str,
        action: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_action = action.lower().strip()
        if device_type in {"OnOffLight", "DimmableLight", "OnOffPlugInUnit", "Generic"}:
            if normalized_action in {"turn_on", "on"}:
                return {"on": True}
            if normalized_action in {"turn_off", "off"}:
                return {"on": False}
            if normalized_action == "toggle":
                return {"on": not bool(payload.get("on", False))}
            if normalized_action == "set_level":
                return {"brightness": max(0, min(100, int(payload.get("brightness", 0))))}
            if normalized_action == "set_color":
                return {"color": str(payload.get("color", "#ffffff"))}

        if device_type == "Switch":
            if normalized_action in {"turn_on", "on"}:
                return {"on": True}
            if normalized_action in {"turn_off", "off"}:
                return {"on": False}
            if normalized_action == "toggle":
                return {"on": not bool(payload.get("on", False))}

        if device_type == "DoorLock":
            if normalized_action == "lock":
                return {"locked": True}
            if normalized_action == "unlock":
                return {"locked": False}

        if device_type == "WindowCovering":
            if normalized_action == "open":
                return {"open": True, "position": 100}
            if normalized_action == "close":
                return {"open": False, "position": 0}
            if normalized_action == "stop":
                return {"stopped": True}
            if normalized_action == "set_position":
                position = max(0, min(100, int(payload.get("position", 0))))
                return {"position": position, "open": position > 0}

        if device_type == "Fan":
            if normalized_action in {"turn_on", "on"}:
                return {"on": True}
            if normalized_action in {"turn_off", "off"}:
                return {"on": False}
            if normalized_action == "toggle":
                return {"on": not bool(payload.get("on", False))}
            if normalized_action == "set_speed":
                return {"speed": max(0, min(100, int(payload.get("speed", 0))))}

        if device_type == "Thermostat" and normalized_action == "set_temperature":
            return {"target_temperature": float(payload.get("target_temperature", payload.get("temperature", 21.0)))}

        if device_type in {"TemperatureSensor", "RelativeHumiditySensor", "AirQualitySensor", "ContactSensor", "OccupancySensor", "SmokeCoAlarm"}:
            if normalized_action == "refresh":
                import random
                res = {"last_refreshed": _now_iso()}
                if device_type == "TemperatureSensor":
                    res["temperature"] = round(random.uniform(18.0, 26.0), 1)
                elif device_type == "RelativeHumiditySensor":
                    res["humidity"] = round(random.uniform(30.0, 70.0), 1)
                elif device_type == "AirQualitySensor":
                    res["aqi"] = round(random.uniform(5.0, 50.0), 1)
                return res

        return {"last_action": action, "last_payload": payload}

    def profile_for(self, device_type: str) -> MatterProfile:
        return next((profile for profile in self._profiles if profile.device_type == device_type), self._profiles[-1])

    def _resolve_raw_signature(self, payload: dict[str, Any]) -> str:
        for field_name in (
            "raw_matter",
            "matter_signature",
            "signature",
            "raw",
            "qr_code",
            "pairing_code",
            "accessory",
            "description",
        ):
            value = str(payload.get(field_name, "")).strip()
            if value:
                return value
        return ""

    def _resolve_clusters(self, payload: dict[str, Any]) -> list[str]:
        cluster_sources = (
            payload.get("clusters"),
            payload.get("cluster"),
            payload.get("matter_clusters"),
            payload.get("endpoint_clusters"),
            payload.get("capabilities"),
        )
        for value in cluster_sources:
            clusters = self._normalize_cluster_list(value)
            if clusters:
                return clusters

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            clusters = self._normalize_cluster_list(metadata.get("clusters"))
            if clusters:
                return clusters

        return []

    def _normalize_cluster_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    result.append(text)
            return result
        return []

    def _infer_from_clusters_debug(self, clusters: list[str]) -> dict[str, Any]:
        normalized = [cluster.strip().lower() for cluster in clusters if str(cluster).strip()]
        if not normalized:
            return {"device_type": "Generic", "matched": None, "tokens": [], "clusters": clusters}

        cluster_set = set(normalized)

        if "doorlock" in cluster_set:
            return {"device_type": "DoorLock", "matched": "DoorLock", "tokens": normalized, "clusters": clusters}
        if "windowcovering" in cluster_set:
            return {"device_type": "WindowCovering", "matched": "WindowCovering", "tokens": normalized, "clusters": clusters}
        if "fancontrol" in cluster_set:
            return {"device_type": "Fan", "matched": "FanControl", "tokens": normalized, "clusters": clusters}
        if "smokecoalarm" in cluster_set:
            return {"device_type": "SmokeCoAlarm", "matched": "SmokeCoAlarm", "tokens": normalized, "clusters": clusters}
        if "relativehumiditymeasurement" in cluster_set:
            return {"device_type": "RelativeHumiditySensor", "matched": "RelativeHumidityMeasurement", "tokens": normalized, "clusters": clusters}
        if "airquality" in cluster_set:
            return {"device_type": "AirQualitySensor", "matched": "AirQuality", "tokens": normalized, "clusters": clusters}
        if "occupancysensor" in cluster_set:
            return {"device_type": "OccupancySensor", "matched": "OccupancySensor", "tokens": normalized, "clusters": clusters}
        if "contactsensor" in cluster_set:
            return {"device_type": "ContactSensor", "matched": "ContactSensor", "tokens": normalized, "clusters": clusters}
        if "temperaturemeasurement" in cluster_set:
            return {"device_type": "TemperatureSensor", "matched": "TemperatureMeasurement", "tokens": normalized, "clusters": clusters}
        if "thermostat" in cluster_set:
            return {"device_type": "Thermostat", "matched": "Thermostat", "tokens": normalized, "clusters": clusters}
        if "levelcontrol" in cluster_set or "colorcontrol" in cluster_set:
            return {"device_type": "DimmableLight", "matched": "LevelControl/ColorControl", "tokens": normalized, "clusters": clusters}
        if "onoff" in cluster_set:
            return {"device_type": "OnOffLight", "matched": "OnOff", "tokens": normalized, "clusters": clusters}

        return {"device_type": "Generic", "matched": None, "tokens": normalized, "clusters": clusters}

    def _extract_matter_tokens(self, signature: str) -> list[str]:
        normalized = signature.lower().strip()
        if "file:///" in normalized:
            normalized = normalized.rsplit("/", 1)[-1]

        if "matter=" in normalized:
            normalized = normalized.split("matter=", 1)[1]

        normalized = normalized.replace("|", " ").replace("/", " ").replace("-", " ").replace("_", " ").replace("?", " ").replace("=", " ")
        return [token for token in normalized.split() if token]

    def _infer_from_signature_debug(self, signature: str) -> dict[str, Any]:
        tokens = self._extract_matter_tokens(signature)
        haystack = " ".join([signature.lower(), *tokens])
        device_type = self._infer_from_signature(signature)
        return {
            "device_type": device_type,
            "matched": device_type if device_type != "Generic" else None,
            "tokens": tokens,
            "haystack": haystack,
        }

    def _infer_from_signature(self, signature: str) -> str:
        tokens = self._extract_matter_tokens(signature)
        haystack = " ".join([signature.lower(), *tokens])

        explicit_map = {
            "onoffpluginunit": "OnOffPlugInUnit",
            "plug": "OnOffPlugInUnit",
            "outlet": "OnOffPlugInUnit",
            "socket": "OnOffPlugInUnit",
            "dimmablelight": "DimmableLight",
            "colorcontrol": "DimmableLight",
            "colortemp": "DimmableLight",
            "colortemperature": "DimmableLight",
            "rgb": "DimmableLight",
            "rgbw": "DimmableLight",
            "rgbcw": "DimmableLight",
            "light": "OnOffLight",
            "lamp": "OnOffLight",
            "bulb": "OnOffLight",
            "led": "OnOffLight",
            "switch": "Switch",
            "thermostat": "Thermostat",
            "temperature": "TemperatureSensor",
            "temperaturesensor": "TemperatureSensor",
            "relativehumiditysensor": "RelativeHumiditySensor",
            "humidity": "RelativeHumiditySensor",
            "airqualitysensor": "AirQualitySensor",
            "airquality": "AirQualitySensor",
            "contactsensor": "ContactSensor",
            "contact": "ContactSensor",
            "occupancysensor": "OccupancySensor",
            "motion": "OccupancySensor",
            "doorlock": "DoorLock",
            "lock": "DoorLock",
            "windowcovering": "WindowCovering",
            "blind": "WindowCovering",
            "curtain": "WindowCovering",
            "shade": "WindowCovering",
            "fan": "Fan",
            "fancontrol": "Fan",
            "smokecoalarm": "SmokeCoAlarm",
            "smoke": "SmokeCoAlarm",
            "coalarm": "SmokeCoAlarm",
        }

        for token in tokens:
            mapped = explicit_map.get(token)
            if mapped:
                return mapped

        if "colorcontrol" in haystack or "rgb" in haystack:
            return "DimmableLight"
        if any(keyword in haystack for keyword in ["light", "lamp", "bulb", "led", "color temp", "colortemperature", "colortemp"]):
            return "DimmableLight"
        if any(keyword in haystack for keyword in ["thermo", "temperature", "climate"]):
            return "Thermostat"
        if any(keyword in haystack for keyword in ["plug", "outlet", "socket"]):
            return "OnOffPlugInUnit"
        if any(keyword in haystack for keyword in ["air quality", "airquality", "aqi"]):
            return "AirQualitySensor"
        if any(keyword in haystack for keyword in ["humidity", "humid"]):
            return "RelativeHumiditySensor"
        if any(keyword in haystack for keyword in ["temp sensor", "temperature sensor", "tempsensor"]):
            return "TemperatureSensor"
        if any(keyword in haystack for keyword in ["contact", "open", "closed"]):
            return "ContactSensor"
        if any(keyword in haystack for keyword in ["motion", "occupancy", "presence"]):
            return "OccupancySensor"
        if "switch" in haystack:
            return "Switch"
        if any(keyword in haystack for keyword in ["doorlock", "lock"]):
            return "DoorLock"
        if any(keyword in haystack for keyword in ["windowcovering", "blind", "curtain", "shade"]):
            return "WindowCovering"
        if any(keyword in haystack for keyword in ["fan", "fancontrol"]):
            return "Fan"
        if any(keyword in haystack for keyword in ["smoke", "co alarm", "coalarm"]):
            return "SmokeCoAlarm"
        return "Generic"

    def _infer_from_qr(self, qr_code: str) -> str:
        return "Generic"

    def _infer_from_pairing_code(self, pairing_code: str) -> str:
        return "Generic"


class ExternalMatterController:
    def __init__(self, module_name: str) -> None:
        module = importlib.import_module(module_name)
        controller_factory = getattr(module, "MatterControllerAdapter", None)
        self._adapter = controller_factory() if callable(controller_factory) else module

    def profiles(self) -> list[MatterProfile]:
        raw_profiles = self._call("profiles")
        return [MatterProfile(**profile) if isinstance(profile, dict) else profile for profile in raw_profiles]

    def discover(self) -> list[dict[str, Any]]:
        return self._call("discover")

    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("pair", payload)

    def resolve_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        method = getattr(self._adapter, "resolve_pairing", None)
        if callable(method):
            return method(payload)
        return {"device_type": "Generic", "pairing_method": "unknown", "resolved_from": "external"}

    def invoke_command(
        self,
        device_type: str,
        action: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if context is None:
            return self._call("invoke_command", device_type, action, payload)
        return self._call("invoke_command", device_type, action, payload, context)

    def _call(self, method_name: str, *args: Any) -> Any:
        method = getattr(self._adapter, method_name, None)
        if method is None:
            raise RuntimeError(f"External Matter controller does not implement '{method_name}'.")
        return method(*args)


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
        
        # Endpoint 0 is root/Basic Information. Skip to keep device state clean.
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
    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url

    def profiles(self) -> list[MatterProfile]:
        return [MatterProfile(**profile) for profile in self._profile_specs()]

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

        job_id = str(payload.get("_pair_job_id") or payload.get("metadata", {}).get("_pair_job_id") or "").strip()
        if job_id:
            update_job(job_id, status="running", stage="connecting", message="Łączenie z Matter Serverem.")
            append_job_log(job_id, "Nawiązywanie połączenia websocket z kontrolerem Matter.")

        client, session = await self._open_client()
        init_ready = asyncio.Event()
        listen_task = asyncio.create_task(client.start_listening(init_ready))
        try:
            await asyncio.wait_for(init_ready.wait(), timeout=10.0)
            if job_id:
                update_job(job_id, stage="commissioning", message="Komisjonowanie urządzenia.")
                append_job_log(job_id, "Wysłano kod QR lub pairing code do Matter Servera.")
                update_job(job_id, stage="commissioning", message="Oczekiwanie na wynik komisjonowania.")
                append_job_log(job_id, "Jeśli to trwa długo, urządzenie może nie potwierdzać parowania albo kontroler nie widzi go w sieci.")
            try:
                node_data = await asyncio.wait_for(
                    client.commission_with_code(code, network_only=bool(payload.get("pairing_code"))),
                    timeout=180,
                )
            except asyncio.TimeoutError as exc:
                if job_id:
                    update_job(job_id, stage="failed", message="Przekroczono czas oczekiwania na komisjonowanie.")
                    append_job_log(job_id, "Matter Server nie zwrócił wyniku komisjonowania w limicie czasu.")
                raise RuntimeError("Commissioning timed out after 180 seconds. Check whether the device is on the same network and awaiting confirmation.") from exc
            if job_id:
                update_job(job_id, stage="reading_node", message="Odczytuję dane nowego node'a.")
                append_job_log(job_id, "Odebrano odpowiedź z kontrolera, buduję profil urządzenia.")
            node = self._build_node(node_data)
            device_type = self._device_type_from_node(node)
            endpoint_id = self._primary_endpoint_id(node)
            profile = self._profile_for_type(device_type)
            if job_id:
                update_job(job_id, stage="finalizing", message="Zapisuję urządzenie w backendzie.")
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
                listen_task.cancel()
                await listen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            await self._safe_close_client(client, session, job_id=job_id)

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
            except asyncio.CancelledError:
                pass
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
        client = MatterClient(self._ws_url, session)
        return client, session

    async def _safe_close_client(self, client: Any, session: Any, job_id: str | None = None) -> None:
        try:
            await asyncio.wait_for(client.disconnect(), timeout=15)
        except Exception as exc:
            if job_id:
                append_job_log(job_id, f"Ostrzeżenie: nie udało się szybko rozłączyć Matter Servera ({exc}).")

        try:
            await asyncio.wait_for(session.close(), timeout=15)
        except Exception as exc:
            if job_id:
                append_job_log(job_id, f"Ostrzeżenie: nie udało się szybko zamknąć sesji HTTP ({exc}).")

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
            endpoint = node.endpoints.get(self._primary_endpoint_id(node))
            if endpoint is None:
                return "Generic"
            descriptor = endpoint.get_cluster(29)
            if descriptor is None:
                return "Generic"
            for item in getattr(descriptor, "deviceTypeList", []) or []:
                mapped = self._device_type_name(getattr(item, "deviceType", getattr(item, "device_type", None)))
                if mapped != "Generic":
                    return mapped
        except Exception:
            return "Generic"
        return "Generic"

    def _device_type_name(self, device_type_id: Any) -> str:
        mapping = {
            256: "OnOffLight",
            257: "DimmableLight",
            269: "DimmableLight",
            266: "OnOffPlugInUnit",
            263: "OccupancySensor",
            10: "DoorLock",
            514: "WindowCovering",
            512: "Thermostat",
            72: "Thermostat",
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
        # We also save the raw attributes inside metadata of the device for troubleshooting,
        # but return clean, mapped attributes for state representation.
        return {**getattr(profile, "default_attributes", {}), **mapped}

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

class SimulatedMatterController:
    def __init__(self) -> None:
        self._fallback = MockMatterController()

    def profiles(self) -> list[MatterProfile]:
        return self._fallback.profiles()

    def discover(self) -> list[dict[str, Any]]:
        return self._fallback.discover()

    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._fallback.pair(payload)

    def resolve_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._fallback.resolve_pairing(payload)

    def invoke_command(
        self,
        device_type: str,
        action: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._fallback.invoke_command(device_type, action, payload, context)


def load_controller_with_status() -> tuple[MatterController, str | None]:
    app_role = os.getenv("APP_ROLE", "").strip().lower()
    if app_role == "simulator":
        return SimulatedMatterController(), None

    matter_server_url = os.getenv("MATTER_SERVER_WS_URL", "").strip()
    if matter_server_url:
        try:
            return MatterServerControllerAdapter(matter_server_url), None
        except Exception:
            return MockMatterController(), f"Failed to initialize MatterServerControllerAdapter for MATTER_SERVER_WS_URL={matter_server_url!r}."

    module_name = os.getenv("MATTER_CONTROLLER_MODULE", "").strip()
    if module_name:
        try:
            return ExternalMatterController(module_name), None
        except Exception:
            return MockMatterController(), f"Failed to load MATTER_CONTROLLER_MODULE={module_name!r}."

    return MockMatterController(), "No real Matter controller configured. Set MATTER_SERVER_WS_URL or MATTER_CONTROLLER_MODULE."


def load_controller() -> MatterController:
    controller, _ = load_controller_with_status()
    return controller


def load_controller() -> MatterController:
    controller, _ = load_controller_with_status()
    return controller