# Haier Evo Boiler 0.3.0b (pre-release)

This beta improves cloud-connection handling and diagnostics in the TechLine S companion. The bundled upstream integration is patched separately (fork manifest 0.3.16b0, upstream base 0.3.15).

## Included
- GET and POST diagnostics require Home Assistant authentication; both remain disabled by default.
- Boiler availability now reflects the Evo WebSocket and device's last reported online status; after a reconnect the cached state is refreshed from REST.
- Commands no longer optimistically update displayed values. Transport failures are propagated and no commands are silently retried.
- Alarm detection only reads explicit alarm-related fields, not arbitrary numeric telemetry.
- Fixed config options compatibility with HA 2026.9+.
- Offline regression tests.

## Installation / rollback
Back up HA and update BOTH folders: `custom_components/haier_evo` and `custom_components/haier_evo_boiler`; then restart HA. To roll back, restore both together from the same prior release.

## Deferred
Gas commissioning, actual command acknowledgements, fault-message schema and clearing semantics, and real device reachability during cloud WebSocket uptime remain unverified. This cloud integration is not a substitute for the boiler's hardware safety and freeze protection.
