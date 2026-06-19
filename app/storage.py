from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sql_text_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass
class Device:
    id: str
    name: str
    vendor: str
    device_type: str
    node_id: str
    status: str
    endpoint: str
    clusters: list[str]
    attributes: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    last_seen_at: str
    room_id: str = ""


@dataclass
class Room:
    id: str
    name: str
    created_at: str


@dataclass
class Automation:
    id: str
    name: str
    trigger_device_id: str
    trigger_attribute: str
    trigger_value: Any
    action_device_id: str
    action_command: str
    action_payload: dict[str, Any]
    enabled: bool
    created_at: str
    trigger_operator: str = "=="


class DeviceRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    vendor TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    clusters TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rooms (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS automations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trigger_device_id TEXT NOT NULL,
                    trigger_attribute TEXT NOT NULL,
                    trigger_value TEXT NOT NULL,
                    action_device_id TEXT NOT NULL,
                    action_command TEXT NOT NULL,
                    action_payload TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            existing_automations_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(automations)").fetchall()
            }
            if "trigger_operator" not in existing_automations_columns:
                connection.execute("ALTER TABLE automations ADD COLUMN trigger_operator TEXT NOT NULL DEFAULT '=='")
                
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(devices)").fetchall()
            }
            for column_name, column_type, default_value in [
                ("device_type", "TEXT", "Generic"),
                ("clusters", "TEXT", "[]"),
                ("attributes", "TEXT", "{}"),
                ("last_seen_at", "TEXT", _now_iso()),
                ("room_id", "TEXT", ""),
            ]:
                if column_name not in existing_columns:
                    if isinstance(default_value, str):
                        default_sql = _sql_text_literal(default_value)
                    else:
                        default_sql = _sql_text_literal(str(default_value))
                    connection.execute(
                        f"ALTER TABLE devices ADD COLUMN {column_name} {column_type} NOT NULL DEFAULT {default_sql}"
                    )
            connection.commit()

    def list_devices(self) -> list[Device]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM devices ORDER BY created_at DESC").fetchall()
        return [self._row_to_device(row) for row in rows]

    def get_device(self, device_id: str) -> Device | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return self._row_to_device(row) if row else None

    def get_device_by_node_id(self, node_id: str) -> Device | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM devices WHERE node_id = ?", (node_id,)).fetchone()
        return self._row_to_device(row) if row else None

    def create_device(
        self,
        name: str,
        vendor: str,
        endpoint: str,
        node_id: str | None = None,
        device_type: str = "Generic",
        clusters: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "discovered",
        room_id: str = "",
    ) -> Device:
        now = _now_iso()
        device = Device(
            id=str(uuid4()),
            name=name,
            vendor=vendor,
            device_type=device_type,
            node_id=node_id or f"node-{uuid4().hex[:8]}",
            status=status,
            endpoint=endpoint,
            clusters=clusters or [],
            attributes=attributes or {},
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
            last_seen_at=now,
            room_id=room_id,
        )
        with self.lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO devices (id, name, vendor, device_type, node_id, status, endpoint, clusters, attributes, metadata, created_at, updated_at, last_seen_at, room_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device.id,
                    device.name,
                    device.vendor,
                    device.device_type,
                    device.node_id,
                    device.status,
                    device.endpoint,
                    json.dumps(device.clusters),
                    json.dumps(device.attributes),
                    json.dumps(device.metadata),
                    device.created_at,
                    device.updated_at,
                    device.last_seen_at,
                    device.room_id,
                ),
            )
            connection.commit()
        return device

    def update_device_status(self, device_id: str, status: str) -> Device | None:
        device = self.get_device(device_id)
        if device is None:
            return None

        updated_at = _now_iso()
        with self.lock, self._connect() as connection:
            connection.execute(
                "UPDATE devices SET status = ?, updated_at = ? WHERE id = ?",
                (status, updated_at, device_id),
            )
            connection.commit()

        device.status = status
        device.updated_at = updated_at
        device.last_seen_at = updated_at
        return device

    def update_device_state(self, device_id: str, attributes: dict[str, Any]) -> Device | None:
        device = self.get_device(device_id)
        if device is None:
            return None

        merged_attributes = {**device.attributes, **attributes}
        updated_at = _now_iso()
        with self.lock, self._connect() as connection:
            connection.execute(
                "UPDATE devices SET attributes = ?, updated_at = ?, last_seen_at = ? WHERE id = ?",
                (json.dumps(merged_attributes), updated_at, updated_at, device_id),
            )
            connection.commit()

        device.attributes = merged_attributes
        device.updated_at = updated_at
        device.last_seen_at = updated_at
        return device

    def update_device_profile(
        self,
        device_id: str,
        *,
        device_type: str | None = None,
        clusters: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> Device | None:
        device = self.get_device(device_id)
        if device is None:
            return None

        updated_device_type = device.device_type if device_type is None else device_type
        updated_clusters = device.clusters if clusters is None else clusters
        updated_metadata = {**device.metadata, **(metadata or {})}
        updated_status = device.status if status is None else status
        updated_at = _now_iso()

        with self.lock, self._connect() as connection:
            connection.execute(
                "UPDATE devices SET device_type = ?, clusters = ?, metadata = ?, status = ?, updated_at = ?, last_seen_at = ? WHERE id = ?",
                (
                    updated_device_type,
                    json.dumps(updated_clusters),
                    json.dumps(updated_metadata),
                    updated_status,
                    updated_at,
                    updated_at,
                    device_id,
                ),
            )
            connection.commit()

        device.device_type = updated_device_type
        device.clusters = updated_clusters
        device.metadata = updated_metadata
        device.status = updated_status
        device.updated_at = updated_at
        device.last_seen_at = updated_at
        return device

    def delete_device(self, device_id: str) -> bool:
        with self.lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            connection.commit()
        return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _row_to_device(self, row: sqlite3.Row) -> Device:
        def _json_value(column_name: str, default_value: Any) -> Any:
            value = row[column_name] if column_name in row.keys() else default_value
            if value in (None, ""):
                return default_value
            return json.loads(value) if isinstance(default_value, (list, dict)) else value

        return Device(
            id=row["id"],
            name=row["name"],
            vendor=row["vendor"],
            device_type=row["device_type"] if "device_type" in row.keys() and row["device_type"] else "Generic",
            node_id=row["node_id"],
            status=row["status"],
            endpoint=row["endpoint"],
            clusters=_json_value("clusters", []),
            attributes=_json_value("attributes", {}),
            metadata=_json_value("metadata", {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_seen_at=row["last_seen_at"] if "last_seen_at" in row.keys() and row["last_seen_at"] else row["updated_at"],
            room_id=row["room_id"] if "room_id" in row.keys() and row["room_id"] else "",
        )

    # Room management
    def list_rooms(self) -> list[Room]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM rooms ORDER BY created_at DESC").fetchall()
        return [Room(id=row["id"], name=row["name"], created_at=row["created_at"]) for row in rows]

    def get_room(self, room_id: str) -> Room | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        return Room(id=row["id"], name=row["name"], created_at=row["created_at"]) if row else None

    def create_room(self, name: str) -> Room:
        now = _now_iso()
        room = Room(id=str(uuid4()), name=name, created_at=now)
        with self.lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO rooms (id, name, created_at) VALUES (?, ?, ?)",
                (room.id, room.name, room.created_at),
            )
            connection.commit()
        return room

    def delete_room(self, room_id: str) -> bool:
        with self.lock, self._connect() as connection:
            # First, set room_id to empty for all devices in this room
            connection.execute("UPDATE devices SET room_id = '' WHERE room_id = ?", (room_id,))
            cursor = connection.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
            connection.commit()
        return cursor.rowcount > 0

    def assign_device_to_room(self, device_id: str, room_id: str | None) -> Device | None:
        device = self.get_device(device_id)
        if device is None:
            return None
        
        target_room_id = room_id or ""
        updated_at = _now_iso()
        with self.lock, self._connect() as connection:
            connection.execute(
                "UPDATE devices SET room_id = ?, updated_at = ? WHERE id = ?",
                (target_room_id, updated_at, device_id),
            )
            connection.commit()
        
        device.room_id = target_room_id
        device.updated_at = updated_at
        return device

    # Automation management
    def list_automations(self) -> list[Automation]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM automations ORDER BY created_at DESC").fetchall()
        return [self._row_to_automation(row) for row in rows]

    def get_automation(self, automation_id: str) -> Automation | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM automations WHERE id = ?", (automation_id,)).fetchone()
        return self._row_to_automation(row) if row else None

    def create_automation(
        self,
        name: str,
        trigger_device_id: str,
        trigger_attribute: str,
        trigger_value: Any,
        action_device_id: str,
        action_command: str,
        action_payload: dict[str, Any] | None = None,
        enabled: bool = True,
        trigger_operator: str = "==",
    ) -> Automation:
        now = _now_iso()
        automation = Automation(
            id=str(uuid4()),
            name=name,
            trigger_device_id=trigger_device_id,
            trigger_attribute=trigger_attribute,
            trigger_value=trigger_value,
            action_device_id=action_device_id,
            action_command=action_command,
            action_payload=action_payload or {},
            enabled=enabled,
            created_at=now,
            trigger_operator=trigger_operator,
        )
        with self.lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO automations (id, name, trigger_device_id, trigger_attribute, trigger_operator, trigger_value, action_device_id, action_command, action_payload, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    automation.id,
                    automation.name,
                    automation.trigger_device_id,
                    automation.trigger_attribute,
                    automation.trigger_operator,
                    json.dumps(automation.trigger_value),
                    automation.action_device_id,
                    automation.action_command,
                    json.dumps(automation.action_payload),
                    1 if automation.enabled else 0,
                    automation.created_at,
                ),
            )
            connection.commit()
        return automation

    def delete_automation(self, automation_id: str) -> bool:
        with self.lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM automations WHERE id = ?", (automation_id,))
            connection.commit()
        return cursor.rowcount > 0

    def update_automation_status(self, automation_id: str, enabled: bool) -> Automation | None:
        automation = self.get_automation(automation_id)
        if automation is None:
            return None

        with self.lock, self._connect() as connection:
            connection.execute(
                "UPDATE automations SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, automation_id),
            )
            connection.commit()

        automation.enabled = enabled
        return automation

    def _row_to_automation(self, row: sqlite3.Row) -> Automation:
        return Automation(
            id=row["id"],
            name=row["name"],
            trigger_device_id=row["trigger_device_id"],
            trigger_attribute=row["trigger_attribute"],
            trigger_value=json.loads(row["trigger_value"]),
            action_device_id=row["action_device_id"],
            action_command=row["action_command"],
            action_payload=json.loads(row["action_payload"]),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            trigger_operator=row["trigger_operator"] if "trigger_operator" in row.keys() else "==",
        )
