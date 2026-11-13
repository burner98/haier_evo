# Boiler 0.4.0b1 — upstream 2.0.0

Based on and7ey/haier_evo v2.0.0, commit a0a16eda5e4979eafd38284524535e9f60dfd322.
The base integration stays at 2.0.0; companion haier_evo_boiler is 0.4.0b1.

- Awaited aiohttp/asyncio transport and entry.runtime_data for both integrations.
- Native GB transport keeps descriptions, REST refreshes and WebSocket pushes live without duplicate entities.
- Companion uses add_listener and removes it on unload, without monkeypatching source methods.
- The same 10 unique_ids, device identifiers, entity names and platform keys remain. Existing registry entity_ids are reused.
- Commands require a live cloud, online boiler and synchronized state. Reconnects require a fresh REST read; stale REST cannot overwrite a newer push. Values are never changed optimistically.
- CI runs the complete upstream suite plus boiler regression tests inside HA 2026.10.4 and 2026.11.1. Publication requires both versions and lint to pass.

## Installation and rollback

This release does not deploy to any installed Home Assistant instance.
Before a future installation, make and download a full HA backup, including `.storage`, the legacy `haier_evo` token file if present, and both custom component directories. Keep it securely: it contains credentials.
Install BOTH directories from the release archive as a pair and restart HA. Do not delete or recreate either integration or its entity registry entries.

Rollback baseline: burner98/haier_evo commit 7ff38716f4c96e81ff47a20775990ec4247ff242 (base 0.3.16b0, companion 0.3.0).
Restore both component directories AND the pre-upgrade HA backup together, then restart. Upstream 2.0.0 migrates legacy credentials into entry-specific storage and may remove the old token file/password: restoring code alone is not a complete rollback from this 0.x fork. Retain the original backup until the migration is accepted.

## Checks without running gas

All automated tests use synthetic device descriptions and mocked cloud transport; they never contact the installed boiler or an EVO account. Verify ten existing entities, saved entity_ids, offline/unavailable behavior, alarm parsing and reconnect reconciliation in an isolated HA test instance.
Do not send power/heating/setpoint commands to a real boiler merely to test this release. No ignition, combustion, real fault reset or live gas behavior has been verified. Any later hardware check follows the manufacturer's commissioning procedure with a qualified installer. This remains a prerelease until commissioning.
