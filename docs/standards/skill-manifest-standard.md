# Skill Manifest Standard

An uploaded Skill ZIP may omit the root `manifest.json`; after archive validation, the backend adds
the canonical instruction-only manifest `{}` before storing the draft. When an uploaded manifest is
present, the backend parses it strictly and rejects the upload if it does not conform. `SKILL.md` owns
name and description; manifest identity fields are rejected. Old `skyler.manifest.json` and
`parrot.manifest.json` files are rejected rather than silently interpreted.

`manifest.json` only declares execution behavior. Its supported fields are `execute`, `runtime`,
`entrypoint`, `timeout_seconds`, `network_enabled`, and `env`. `execute` defaults to `false`; an
instruction-only Skill therefore uses `{}` or `{ "execute": false }`. When `execute` is true,
`runtime` must be `python`, `node`, or `shell`, and `entrypoint` must be a safe relative path ending
in `.py`, `.js`/`.mjs`/`.cjs`, or `.sh`.

The backend `SkillManifest` document is the only parser and serializer for this protocol. Package
inspection, database-backed execution, builds, and package-file mutations must use it. Adding,
replacing, or removing the root manifest uses the dedicated manifest mutation functions; generic
archive editing must not implement its own JSON parsing, defaults, or serialization rules.

The editor hides a single Skill root only for entries beneath that root. ZIP entries outside it,
including macOS `__MACOSX` sidecars, retain their archive paths and can be read, replaced, or deleted
by returning that exact path to the backend. This prevents a display-only relative path from becoming
an unresolvable mutation target.

`env` contains only non-sensitive values. The platform rejects reserved runtime,
interpreter, loader, PATH, HOME and `PARROT_*` variables. Credentials belong in authorized
configuration resources, never manifests.

`network_enabled` defaults to false and directly controls Bubblewrap network isolation. There is no
host allowlist field until a separately enforced egress policy exists.

Input/output schemas, risk levels, side-effect labels, and identity metadata do not belong in the
manifest. Runtime accepts a JSON object written to the designated output file, or bounded stdout
when no output file is produced.

Published packages that used the retired `schema_version` / `runtime` / `permissions` format remain
readable at runtime to preserve immutable historical versions. New imports, draft edits, and
publishes must use the current compact format.

Executable Skill publication freezes the validated draft ZIP directly:

```text
draft ZIP -> explicit publish -> immutable published ZIP -> runtime
```

The unified TaskIQ worker may create an immutable artifact for dependencies. Runtime prefers a
matching artifact when present and otherwise reads the immutable published ZIP. Runtime never
installs dependencies: a direct-published Skill must be self-contained, while Python and Node
dependencies require the optional prebuild path. Every source edit invalidates any prior artifact.
