from __future__ import annotations

from threading import Thread, Lock

from flask import Blueprint, current_app, jsonify, render_template, request

from .controller import MockMatterController, map_raw_attributes
from .matter import MatterHubService
from .pairing_jobs import append_job_log, complete_job, create_job, fail_job, get_job, job_to_dict, update_job
import time

api = Blueprint("api", __name__)

_sync_lock = Lock()
_sync_started = False

import asyncio

import asyncio
import time
from flask import current_app

api = Blueprint("api", __name__)

_sync_lock = Lock()
_sync_thread = None

def _run_background_sync(app_instance):
    with app_instance.app_context():
        controller = current_app.extensions["matter_controller"]
        while True:
            try:
                # Sprawdzenie czy kontroler jest zainicjalizowany
                if hasattr(controller, "_ready_event") and not controller._ready_event.is_set():
                    time.sleep(5)
                    continue
                
                repo = _repository()
                devices = repo.list_devices()
                
                for device in devices:
                    if device.status in {"connected", "paired"}:
                        try:
                            # ODŁĄCZYŁEM Refresh! Czytamy tylko z pamięci (cache)
                            node_id = int(device.metadata.get("matter_node_id", 0))
                            if hasattr(controller, "_client") and controller._client:
                                node = controller._client.get_node(node_id)
                                if node:
                                    # Pobranie stanu z lokalnej pamięci (cache)
                                    state_patch = map_raw_attributes(node.node_data.attributes)
                                    if state_patch and state_patch != device.attributes:
                                        repo.update_device_state(device.id, state_patch)
                                        # Automatyzacje
                                        check_and_run_automations(device.id, state_patch)
                        except Exception as inner_e:
                            print(f"Error syncing device {device.id}: {inner_e}")
                            continue
                time.sleep(4.0)
            except Exception as e:
                print(f"Sync thread crashed: {e}")
                time.sleep(10)
            
@api.before_request
def ensure_sync_thread():
    global _sync_thread
    if _sync_thread is None or not _sync_thread.is_alive():
        with _sync_lock:
            if _sync_thread is None or not _sync_thread.is_alive():
                app_instance = current_app._get_current_object()
                _sync_thread = Thread(target=_run_background_sync, args=(app_instance,), daemon=True)
                _sync_thread.start()
                print("Background sync thread started.")

def _normalize_pairing_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    raw_qr = str(normalized.get("qr_code") or "").strip()

    if raw_qr.startswith("matter://"):
        candidate = raw_qr.removeprefix("matter://").strip()
        if candidate.isdigit():
            normalized["pairing_code"] = candidate
            normalized["qr_code"] = ""
        else:
            normalized["qr_code"] = candidate

    return normalized


def _repository():
    return current_app.extensions["device_repository"]


def _service() -> MatterHubService:
    return MatterHubService(current_app.extensions["matter_controller"])


@api.get("/")
def index():
    return render_template("index.html")


@api.get("/swagger")
def swagger_ui():
    return render_template("swagger.html")



@api.get("/api/debug/matter")
def debug_matter():
    controller = current_app.extensions["matter_controller"]
    if not hasattr(controller, "_client") or not controller._client:
        return jsonify({"error": "No client available"})
    
    from .controller import _jsonable
    nodes = controller._client.get_nodes()
    nodes_info = []
    for node in nodes:
        nodes_info.append({
            "node_id": node.node_id,
            "available": node.available,
            "attributes_count": len(getattr(node.node_data, "attributes", {})),
            "attributes": _jsonable(node.node_data.attributes)
        })
        
    return jsonify({
        "connected": controller._client.connection.connected if hasattr(controller._client, "connection") else False,
        "nodes_count": len(nodes),
        "nodes": nodes_info
    })


@api.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "controller": {
                "type": type(current_app.extensions["matter_controller"]).__name__,
                "error": current_app.extensions.get("matter_controller_error"),
            },
        }
    )


@api.get("/api/devices")
def list_devices():
    service = _service()
    devices = []
    for device in _repository().list_devices():
        d = device.__dict__.copy()
        try:
            d["actions"] = service.allowed_actions(device.device_type)
        except Exception:
            d["actions"] = []
        devices.append(d)
    return jsonify({"devices": devices})


@api.post("/api/devices")
def create_device():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"error": "Field 'name' is required."}), 400

    device = _repository().create_device(
        name=name,
        vendor=payload.get("vendor", "Unknown Vendor"),
        endpoint=payload.get("endpoint", "1"),
        device_type=payload.get("device_type", "Generic"),
        clusters=payload.get("clusters", []),
        attributes=payload.get("attributes", {}),
        metadata=payload.get("metadata", {}),
        status=payload.get("status", "discovered"),
    )
    return jsonify({"device": device.__dict__}), 201


@api.get("/api/devices/<device_id>")
def get_device(device_id: str):
    device = _repository().get_device(device_id)
    if device is None:
        return jsonify({"error": "Device not found."}), 404
    return jsonify({"device": device.__dict__})


@api.get("/api/devices/<device_id>/state")
def device_state(device_id: str):
    device = _repository().get_device(device_id)
    if device is None:
        return jsonify({"error": "Device not found."}), 404
    return jsonify(
        {
            "device_id": device.id,
            "device_type": device.device_type,
            "status": device.status,
            "attributes": device.attributes,
            "metadata": device.metadata,
            "updated_at": device.updated_at,
            "last_seen_at": device.last_seen_at,
        }
    )


@api.get("/api/devices/<device_id>/actions")
def device_actions(device_id: str):
    device = _repository().get_device(device_id)
    if device is None:
        return jsonify({"error": "Device not found."}), 404
    service = _service()
    return jsonify({"device_id": device.id, "device_type": device.device_type, "actions": service.allowed_actions(device.device_type)})


@api.post("/api/devices/<device_id>/connect")
def connect_device(device_id: str):
    device = _repository().update_device_status(device_id, "connected")
    if device is None:
        return jsonify({"error": "Device not found."}), 404
    return jsonify({"device": device.__dict__})


@api.post("/api/devices/<device_id>/disconnect")
def disconnect_device(device_id: str):
    device = _repository().update_device_status(device_id, "disconnected")
    if device is None:
        return jsonify({"error": "Device not found."}), 404
    return jsonify({"device": device.__dict__})


import threading
from typing import Any

_local_automation = threading.local()

def check_and_run_automations(device_id: str, state_patch: dict[str, Any]):
    if getattr(_local_automation, "running", False):
        return
    _local_automation.running = True
    try:
        repo = _repository()
        automations = repo.list_automations()
        for aut in automations:
            if not aut.enabled or aut.trigger_device_id != device_id:
                continue
            
            if aut.trigger_attribute in state_patch:
                new_value = state_patch[aut.trigger_attribute]
                
                # Dynamic validation based on trigger_operator
                op = getattr(aut, "trigger_operator", "==")
                matched = False
                
                # Attempt to normalize trigger_value and new_value to same type (e.g. bool, float)
                normalized_trigger_val = aut.trigger_value
                normalized_new_val = new_value
                
                # Check for booleans
                if isinstance(new_value, bool) or str(new_value).lower() in ("true", "false"):
                    b_new = bool(new_value) if isinstance(new_value, bool) else (str(new_value).lower() == "true")
                    b_trig = normalized_trigger_val
                    if str(normalized_trigger_val).lower() in ("true", "on", "yes", "1"):
                        b_trig = True
                    elif str(normalized_trigger_val).lower() in ("false", "off", "no", "0"):
                        b_trig = False
                    normalized_new_val = b_new
                    normalized_trigger_val = b_trig
                # Check for numbers
                else:
                    try:
                        normalized_new_val = float(new_value)
                        normalized_trigger_val = float(aut.trigger_value)
                    except (ValueError, TypeError):
                        normalized_new_val = str(new_value).strip().lower()
                        normalized_trigger_val = str(aut.trigger_value).strip().lower()

                if op == "==":
                    matched = (normalized_new_val == normalized_trigger_val)
                elif op == "!=":
                    matched = (normalized_new_val != normalized_trigger_val)
                elif op == ">":
                    try:
                        matched = (normalized_new_val > normalized_trigger_val)
                    except TypeError:
                        pass
                elif op == "<":
                    try:
                        matched = (normalized_new_val < normalized_trigger_val)
                    except TypeError:
                        pass
                elif op == ">=":
                    try:
                        matched = (normalized_new_val >= normalized_trigger_val)
                    except TypeError:
                        pass
                elif op == "<=":
                    try:
                        matched = (normalized_new_val <= normalized_trigger_val)
                    except TypeError:
                        pass

                if matched:
                    action_device = repo.get_device(aut.action_device_id)
                    if not action_device:
                        continue
                    
                    service = _service()
                    allowed_actions = service.allowed_actions(action_device.device_type)
                    if aut.action_command in allowed_actions:
                        # Real invoke_command triggers physical action on device!
                        action_state_patch = service.invoke_command(
                            action_device.device_type,
                            aut.action_command,
                            aut.action_payload or {},
                            context=action_device.metadata,
                        )
                        repo.update_device_state(aut.action_device_id, action_state_patch)
                        # Avoid infinite loops, but allow chain execution
                        check_and_run_automations(aut.action_device_id, action_state_patch)
    except Exception as e:
        current_app.logger.error(f"Error running automations: {e}")
    finally:
        _local_automation.running = False


@api.post("/api/devices/<device_id>/command")
def command_device(device_id: str):
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    if not action:
        return jsonify({"error": "Field 'action' is required."}), 400

    device = _repository().get_device(device_id)
    if device is None:
        return jsonify({"error": "Device not found."}), 404

    service = _service()
    allowed_actions = service.allowed_actions(device.device_type)
    if action not in allowed_actions:
        return jsonify({"error": f"Action '{action}' is not supported for device type '{device.device_type}'.", "allowed_actions": allowed_actions}), 400

    state_patch = service.invoke_command(
        device.device_type,
        action,
        payload.get("payload") or {},
        context=device.metadata,
    )
    updated_device = _repository().update_device_state(device_id, state_patch)
    if updated_device is None:
        return jsonify({"error": "Device not found."}), 404
    
    # Run automations
    check_and_run_automations(device_id, state_patch)
    
    return jsonify({"device": updated_device.__dict__, "applied": state_patch})


@api.post("/api/devices/<device_id>/delete")
def delete_device(device_id: str):
    deleted = _repository().delete_device(device_id)
    if not deleted:
        return jsonify({"error": "Device not found."}), 404
    return jsonify({"deleted": True})


@api.get("/api/matter/discover")
def discover_devices():
    service = _service()
    return jsonify({"discoveries": service.discover(), "profiles": service.profile_dicts()})


@api.get("/api/matter/profiles")
def matter_profiles():
    return jsonify({"profiles": _service().profile_dicts()})


@api.get("/api/device-types")
def device_types():
    profiles = _service().profile_dicts()
    return jsonify({"device_types": [{"device_type": profile["device_type"], "label": profile["label"]} for profile in profiles]})


@api.post("/api/matter/resolve")
def resolve_pairing():
    payload = request.get_json(silent=True) or {}
    service = _service()
    resolved = service.resolve_pairing(payload)
    device_type = resolved["device_type"]
    profile = service.profile_for(device_type)
    return jsonify(
        {
            "device_type": device_type,
            "pairing_method": resolved["pairing_method"],
            "resolved_from": resolved["resolved_from"],
            "label": profile.label,
            "actions": profile.actions,
            "clusters": profile.clusters,
            "default_attributes": profile.default_attributes,
        }
    )


@api.post("/api/matter/resolve-debug")
def resolve_pairing_debug():
    payload = request.get_json(silent=True) or {}
    service = _service()
    resolved = service.resolve_pairing(payload)
    profile = service.profile_for(resolved.get("device_type", "Generic"))
    return jsonify({
        "payload": payload,
        "resolved": resolved,
        "profile": {
            "device_type": profile.device_type,
            "label": profile.label,
            "actions": profile.actions,
            "clusters": profile.clusters,
            "default_attributes": profile.default_attributes,
        },
    })


@api.post("/api/matter/pair")
def pair_device():
    payload = _normalize_pairing_payload(request.get_json(silent=True) or {})
    if not payload.get("name"):
        return jsonify({"error": "Field 'name' is required."}), 400

    service = _service()
    job = create_job()
    update_job(job.job_id, status="running", stage="starting", message="Przygotowuję parowanie urządzenia.")
    append_job_log(job.job_id, "Odebrano żądanie parowania z formularza.")

    app = current_app._get_current_object()

    def _run_pairing() -> None:
        with app.app_context():
            try:
                update_job(job.job_id, stage="resolving", message="Ustalanie typu urządzenia.")
                append_job_log(job.job_id, "Sprawdzam kod QR lub pairing code w kontrolerze Matter.")
                worker_payload = {**payload, "_pair_job_id": job.job_id}
                pair_data = service.pair(worker_payload)
                final_device_type = pair_data["device_type"]
                metadata = pair_data.get("metadata", {})
                if metadata.get("controller") == "matter-server" and final_device_type == "Generic":
                    raise RuntimeError("Real Matter controller returned no device type. Configure a working MATTER_SERVER_WS_URL controller.")

                final_clusters = pair_data.get("clusters") or ["Identify"]
                final_metadata = {
                    **metadata,
                    "pairing_pending": False,
                    "pairing_method": metadata.get("pairing_method", "pairing_code"),
                    "resolved_from": metadata.get("resolved_from", "pairing_code"),
                    "pairing_completed": True,
                }

                pair_data = {
                    **pair_data,
                    "device_type": final_device_type,
                    "clusters": final_clusters,
                    "metadata": final_metadata,
                    "attributes": pair_data.get("attributes", {}),
                }

                update_job(job.job_id, stage="saving", message="Zapisuję urządzenie w backendzie.")
                device = _repository().create_device(
                    name=pair_data["name"],
                    vendor=pair_data["vendor"],
                    node_id=str(metadata.get("matter_node_id") or metadata.get("node_id") or ""),
                    device_type=pair_data["device_type"],
                    endpoint=pair_data["endpoint"],
                    clusters=pair_data["clusters"],
                    attributes=pair_data["attributes"],
                    metadata=pair_data["metadata"],
                    status="paired",
                )
                complete_job(job.job_id, {"device": device.__dict__})
            except Exception as exc:
                fail_job(job.job_id, str(exc))

    Thread(target=_run_pairing, daemon=True).start()
    return jsonify({"job_id": job.job_id, "status": job.status, "stage": job.stage, "message": job.message}), 202


@api.get("/api/matter/pair/<job_id>")
def pairing_status(job_id: str):
    existing_job = get_job(job_id)
    if existing_job is None:
                return jsonify({"error": "Pairing job not found."}), 404
    return jsonify(job_to_dict(existing_job))


@api.get("/api/rooms")
def list_rooms():
    rooms = [room.__dict__ for room in _repository().list_rooms()]
    return jsonify({"rooms": rooms})


@api.post("/api/rooms")
def create_room():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"error": "Field 'name' is required."}), 400
    room = _repository().create_room(name=name)
    return jsonify({"room": room.__dict__}), 201


@api.post("/api/rooms/<room_id>/delete")
def delete_room(room_id: str):
    deleted = _repository().delete_room(room_id)
    if not deleted:
        return jsonify({"error": "Room not found."}), 404
    return jsonify({"deleted": True})


@api.post("/api/devices/<device_id>/room")
def assign_device_to_room(device_id: str):
    payload = request.get_json(silent=True) or {}
    room_id = payload.get("room_id")
    device = _repository().assign_device_to_room(device_id, room_id)
    if device is None:
        return jsonify({"error": "Device not found."}), 404
    return jsonify({"device": device.__dict__})


@api.get("/api/automations")
def list_automations():
    automations = [aut.__dict__ for aut in _repository().list_automations()]
    return jsonify({"automations": automations})


@api.post("/api/automations")
def create_automation():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    trigger_device_id = payload.get("trigger_device_id")
    trigger_attribute = payload.get("trigger_attribute")
    trigger_value = payload.get("trigger_value")
    trigger_operator = payload.get("trigger_operator", "==")
    action_device_id = payload.get("action_device_id")
    action_command = payload.get("action_command")
    action_payload = payload.get("action_payload") or {}

    if not all([name, trigger_device_id, trigger_attribute, action_device_id, action_command]):
        return jsonify({"error": "Fields 'name', 'trigger_device_id', 'trigger_attribute', 'action_device_id', and 'action_command' are required."}), 400

    automation = _repository().create_automation(
        name=name,
        trigger_device_id=trigger_device_id,
        trigger_attribute=trigger_attribute,
        trigger_value=trigger_value,
        trigger_operator=trigger_operator,
        action_device_id=action_device_id,
        action_command=action_command,
        action_payload=action_payload,
        enabled=payload.get("enabled", True),
    )
    return jsonify({"automation": automation.__dict__}), 201


@api.post("/api/automations/<automation_id>/delete")
def delete_automation(automation_id: str):
    deleted = _repository().delete_automation(automation_id)
    if not deleted:
        return jsonify({"error": "Automation not found."}), 404
    return jsonify({"deleted": True})


@api.post("/api/automations/<automation_id>/toggle")
def toggle_automation(automation_id: str):
    payload = request.get_json(silent=True) or {}
    enabled = payload.get("enabled", True)
    automation = _repository().update_automation_status(automation_id, enabled)
    if automation is None:
        return jsonify({"error": "Automation not found."}), 404
    return jsonify({"automation": automation.__dict__})
