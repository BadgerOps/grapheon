# Lessons Learned

Patterns to watch for, mistakes to avoid, and rules discovered through iteration.

## Data Pipeline

- **Always validate parser output against DB state.** The nmap parser may parse ports successfully but fail silently on host-level fields (hostname, OS). Check the DB after imports, not just the parser return value.
- **Clean data at ingestion, not at display.** The ` [ether]` suffix in MAC addresses should have been stripped in the ARP parser, not worked around downstream. Fix at the source.
- **Platform detection order matters.** When multiple platforms share a syntax pattern (Linux and macOS both use `?` for unresolved hostnames in `arp -a`), disambiguate on secondary markers (`[ether]` vs `[ethernet]`/`ifscope`) rather than relying on the first regex match.
- **Non-greedy regex `(.+?)` is dangerous for structured data.** The macOS parser used `(.+?)` to capture MAC addresses, which accidentally consumed the `[ether]` type marker. Use character-class patterns like `([0-9a-fA-F:]+)` for structured fields.
- **Nmap enrichment depends on scan flags.** Running `nmap` without `-O` (OS detection) or `-A` (aggressive mode) produces no hostname/OS data in the XML. The parser is correct — the input data was sparse.

## Visualization

- **Grouping must match the actual network topology.** /24 CIDR grouping is a convenient default but doesn't represent VLANs when multiple VLANs share a subnet range. Use ARP interface data as the ground truth for segments.
- **A map full of identical gray dots is useless.** Always verify that node differentiation (shape, color, label) actually works with real data before calling visualization "done."
- **Never conditionally unmount vis-network's container div.** Returning a different JSX tree (like a loading spinner) removes the container from the DOM while vis-network still has pending callbacks (physics, stabilization). This causes `NotFoundError: The object can not be found here`. Always keep the container mounted and use `display: none` + overlays instead.
- **vis-network `font.bold` expects an object, not a boolean.** Setting `bold: true` on a node's font config can crash vis-network internally. Use `font: { size: 14 }` directly instead.
- **Remove stale state variables after refactors.** `groupBySubnet` was left behind after adding `groupMode`, causing redundant/conflicting params to be sent to the API. Clean up dead state.

## Architecture

- **Derive from existing data before adding new models.** Segment grouping works by querying ARP interface names at map generation time — no `NetworkSegment` model was needed. Avoid schema complexity when runtime derivation is sufficient.
- **Gateway detection is a data enrichment step, not a model concern.** Routers are identified by their MAC appearing as `.1` across multiple subnets — this runs as a migration/enrichment script, not embedded in the ORM.

## Database & Error Handling

- **Model nullable constraints must account for all protocol states.** LISTEN connections have no remote endpoint (`0.0.0.0:*`), so `remote_port` must be `nullable=True`. Always check edge-case protocol states (LISTEN, TIME_WAIT) when defining column constraints.
- **SQLite can't ALTER COLUMN — must recreate the table.** To change a column from NOT NULL to nullable in SQLite, you need to: create a new table with the updated schema, copy data, drop old, rename. The `_make_column_nullable()` helper encapsulates this.
- **Use savepoints (`begin_nested()`) around bulk DB operations.** When processing many records (hosts, connections, ARP), a single IntegrityError puts the entire SQLAlchemy session into a "needs rollback" state. Wrapping in `begin_nested()` creates a savepoint — only the savepoint rolls back on error, and the outer transaction (holding the import_record) stays valid.
- **`PendingRollbackError` is the symptom, not the root cause.** When an `IntegrityError` rolls back the session, any subsequent `db.commit()` fails with `PendingRollbackError`. The fix is upstream: either prevent the constraint violation or use savepoints to isolate the failure.
- **Match API response field names to frontend expectations.** The vendor lookup returned `vendors_updated` but the frontend read `result.updated` → displayed "undefined". Always grep for the field name in both backend and frontend when adding API responses.

## Vendor Lookup

- **`mac-vendor-lookup` package is async-incompatible with uvicorn.** Its sync `MacLookup.lookup()` calls `asyncio.get_event_loop().run_until_complete()` internally, which crashes with "this event loop is already running" inside uvicorn. Fix: read the package's downloaded `mac-vendors.txt` file directly and build a plain dict.
- **Locally administered MACs cannot be OUI-resolved.** If bit 1 of the first octet is set (second hex char is 2/3/6/7/A/B/E/F), the MAC is randomly generated (Tailscale, WireGuard, VMs, Docker). Detect these early and label them rather than reporting "not found."

## Process

- **Check the actual input data before blaming the parser.** The nmap parser appeared broken because hosts had no OS/hostname, but the real issue was that `nmap.xml` was a minimal scan without `-O`/`-A` flags. Always inspect the raw import data.
