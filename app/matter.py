from __future__ import annotations

from typing import Any

from .controller import MatterController, MatterProfile, MockMatterController


class MatterHubService:
    def __init__(self, controller: MatterController | None = None) -> None:
        self.controller = controller or MockMatterController()

    def profile_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "device_type": profile.device_type,
                "label": profile.label,
                "clusters": profile.clusters,
                "actions": profile.actions,
                "default_attributes": profile.default_attributes,
            }
            for profile in self.controller.profiles()
        ]

    def profile_for(self, device_type: str) -> MatterProfile:
        return next((profile for profile in self.controller.profiles() if profile.device_type == device_type), self.controller.profiles()[-1])

    def allowed_actions(self, device_type: str) -> list[str]:
        return list(self.profile_for(device_type).actions)

    def resolve_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.controller.resolve_pairing(payload)

    def profiles(self) -> list[dict[str, Any]]:
        return self.profile_dicts()

    def discover(self) -> list[dict[str, Any]]:
        return self.controller.discover()

    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        resolved = self.resolve_pairing(payload)
        device_type = resolved["device_type"]
        controller_payload = self.controller.pair({**payload, "device_type": device_type})
        final_device_type = controller_payload.get("device_type") or device_type
        profile = self.profile_for(final_device_type)
        return {
            **controller_payload,
            "device_type": final_device_type,
            "endpoint": controller_payload.get("endpoint", payload.get("endpoint", "1")),
            "clusters": controller_payload.get("clusters", payload.get("clusters", profile.clusters)),
            "attributes": {**profile.default_attributes, **controller_payload.get("attributes", {}), **payload.get("attributes", {})},
            "metadata": {
                **controller_payload.get("metadata", {}),
                "pairing_code": payload.get("pairing_code", "manual"),
                "qr_code": payload.get("qr_code", ""),
                "transport": payload.get("transport", "matter"),
                "matter_standard": "1.3",
                "pairing_method": resolved["pairing_method"],
                "resolved_from": resolved["resolved_from"],
            },
        }

    def invoke_command(
        self,
        device_type: str,
        action: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.controller.invoke_command(device_type, action, payload, context)
