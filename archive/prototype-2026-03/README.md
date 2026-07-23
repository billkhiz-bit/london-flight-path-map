# March 2026 prototype — historical artefact, do not run

Preserved 2026-07-19 from the retired OneDrive clone for provenance only.
These files predate the SAM backend, the security hardening waves, and the
Sky Score branding. They are not part of any build or deploy path.

Known issues, kept as-is deliberately (this is a museum piece, not code to fix):

- `london_flight_paths.py` disables TLS certificate verification
  (`ssl.CERT_NONE`) for its OpenSky fetch. The production replacement
  (the removed `live_flights` Lambda, last working commit `a214ba0`)
  used verified HTTPS via `urllib` defaults.
- `samconfig.toml.march-2026` references the pre-hardening March stack.
- `claude-commands/` are the pre-plugin slash commands superseded by
  `.claude/skills/`.

If you need working code for any of this, start from the current
`backend/lambdas/` implementations, not from here.
