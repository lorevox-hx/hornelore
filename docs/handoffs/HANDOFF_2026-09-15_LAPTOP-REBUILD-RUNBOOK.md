# LAPTOP REBUILD RUNBOOK — 2026-09-15

**The procedure actually followed on the laptop.** Derived from `HANDOFF.md` § *NEXT — THE
LAPTOP REBUILD*, corrected against the shipped code on 2026-09-15. Where this file and
prose disagree, **the code citation wins** — every claim below names the line it came from.

**The hard boundary: nothing is deleted until the preservation copy AND the USB packages
both verify, on two different physical devices.**

---

## Corrections folded in (do not re-derive these)

| # | Was | Is | Proof |
|---|---|---|---|
| 1 | `POST /api/people/{id}/retry-erasure` | **`/erase-retry`** | `routers/people.py:317`, `db.py:6483`. `retry-erasure` exists nowhere in the repo. |
| 2 | `--expect <uuid>` once per narrator | **all three in ONE invocation** | `family_root_verify.py:73` — `want, got = set(a.expect), set(ids)`, exact set comparison. Per-narrator calls report the other two as unexpected extras. |
| 3 | 524 / 43 / 66 rows, 280 files = acceptance | **sanity references only** | `--expect-rows` is exact equality (`family_root_verify.py:111`). The fresh pre-erasure export sets the contract. |
| 4 | "five databases in `db/` will trip the Phase 7 gate" | **FALSE — it will not** | `runtime_root.py:78,186-189`: only `KNOWN_DB_NAMES = ("lorevox.sqlite3","hornelore.sqlite3")` participate, zero-byte excluded. `hornelore_evalcopy.sqlite3` and the `backup_*.sqlite3` files are invisible to the gate. **Do not move them.** |

Correction 4 was an error made while drafting this runbook, from reading the handoff's
prose instead of the gate's code. It is recorded rather than quietly dropped because the
instinct it produced — rearranging the data root before preserving it — was the dangerous
part, not the wrong fact.

---

## Fixed facts

| | |
|---|---|
| Repo | `/mnt/c/Users/chris/hornelore` at `origin/main` |
| Laptop `DATA_DIR` | `/mnt/c/hornelore_data` — **the laptop keeps its own root** (`HANDOFF.md:95`) |
| Laptop `DB_NAME` | `hornelore.sqlite3` |
| Christopher | `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2` |
| Kent | `4aa0cc2b-1f27-433a-9152-203bb1f69a55` |
| Janice | `93479171-0b97-4072-bcf0-d44c7f9078ba` |

**`.env.example` shows `/mnt/c/lorevox_data` because that is the DESKTOP's clean Phase 7
root. Do not adopt it here.** Do not copy the desktop `.env` onto the laptop.

---

## ⛔ HARD STOPS — halt and report, do not improvise

1. `git status --short` non-empty before the pull
2. `git pull --ff-only` refuses (divergence, not a speed bump)
3. `describe_root()` reports anything but `problems: []`
4. Any of the three family UUIDs missing from the live database
5. Preservation copy fails file count, DB SHA-256, `rsync --checksum` or `integrity_check`
6. **Only one external device available** — see step 5
7. A fresh export contracts sharply against the 524 / 43 / 66 reference
8. Any package fails `validate`
9. `sha256sum -c` fails on the USB
10. `ids_to_erase.txt` not read and consciously authorized
11. HTTP 207 that `erase-retry` does not complete
12. Restore verification not `MATCHES` / `CLEAN`, or any `compare` not `EQUIVALENT`

---

## 1 · Stop, prove clean, pull

```bash
cd /mnt/c/Users/chris/hornelore
bash scripts/stop_all.sh
git status --short          # non-empty -> STOP
git fetch origin
git log -1 --oneline origin/main
git pull --ff-only origin main
git rev-parse --short HEAD
```

## 2 · Audit shell exports and `.env`

The desktop had `DATA_DIR` exported **twice** in `~/.bashrc`, the second winning, which is
how a narrator landed in an unintended root (`HANDOFF.md:77`). Assume the laptop has its own.

```bash
grep -nE '^[[:space:]]*export[[:space:]]+(DATA_DIR|DB_NAME|HORNELORE_DATA_DIR|DB_PATH)=' \
  ~/.bashrc ~/.profile ~/.bash_profile ~/.bash_login 2>/dev/null \
  || echo "PASS: no profile root exports"

printf 'DATA_DIR=%s\nDB_NAME=%s\n' "${DATA_DIR:-<unset>}" "${DB_NAME:-<unset>}"

grep -nE '^(DATA_DIR|DB_NAME|DB_PATH|HORNELORE_DATA_DIR|UPLOADS_DIR|MEDIA_DIR|AUTHORS_DIR|KNOWLEDGE_DIR|TTS_HOME)=' .env
```

Comment out any profile export found, keeping a timestamped backup of the file. Then
`unset DATA_DIR DB_NAME HORNELORE_DATA_DIR DB_PATH` in the current shell.

## 3 · Identify the authoritative installation

```bash
cd /mnt/c/Users/chris/hornelore
ROOT="$(grep '^DATA_DIR=' .env | tail -1 | cut -d= -f2-)"
DBNAME="$(grep '^DB_NAME=' .env | tail -1 | cut -d= -f2-)"
DB="$ROOT/db/$DBNAME"
printf 'ROOT=%s\nDB=%s\n' "$ROOT" "$DB"

ls -la "$ROOT/db/"

sqlite3 -readonly "$DB" "
  PRAGMA integrity_check;
  SELECT COUNT(*) AS people FROM people;
  SELECT id, display_name FROM people
   WHERE id IN ('a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2',
                '4aa0cc2b-1f27-433a-9152-203bb1f69a55',
                '93479171-0b97-4072-bcf0-d44c7f9078ba')
   ORDER BY display_name;"
```

All three must be present. **Expect roughly 74 people** — the three family narrators plus
~71 development and test narrators. That number matters at step 12.

### Persist the session state NOW

These values are used by every remaining step. A closed terminal must not be able to leave
a stale or empty path in play at the moment something is deleted.

```bash
STATE=/mnt/c/lorevox_packages/laptop-rebuild-session.env
mkdir -p /mnt/c/lorevox_packages
umask 077
printf 'ROOT=%q\nDBNAME=%q\nDB=%q\n' "$ROOT" "$DBNAME" "$DB" > "$STATE"
cat "$STATE"
```

**Every independent shell block from here on begins with:**

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
```

`RUN` / `OUT` are appended at step 8 and `USBDEST` at step 11, so a block that needs them
must run after those steps — sourcing alone will not conjure them.

## 4 · Run the root gate BEFORE touching anything

```bash
cd /mnt/c/Users/chris/hornelore
(
  unset DATA_DIR DB_NAME HORNELORE_DATA_DIR DB_PATH UPLOADS_DIR MEDIA_DIR
  set -a; source .env; set +a
  PYTHONPATH=server/code .venv/bin/python -c \
    "from api import runtime_root as r; import json; print(json.dumps(r.describe_root(), indent=2))"
)
```

Want `problems: []`. **If clean, move nothing.** `hornelore_evalcopy.sqlite3` and the three
`backup_*.sqlite3` files stay exactly where they are — they are audit evidence and the gate
cannot see them (correction 4). If it *does* refuse, `HANDOFF.md:91` names every cause.

## 5 · Preserve the ENTIRE laptop data root — before any change, before any deletion

Phase 7 preserved the desktop's root this way (`HANDOFF.md:75`). **No equivalent copy of the
laptop's root exists.** Step 13 erases ~71 narrators that have no portable package; this is
the only thing standing between them and permanent loss.

**The preservation drive and the package USB MUST be different physical devices.** If only
one external device is available, **stop** — a single lost stick must not be able to take
both the full-root preservation and the only portable copies.

```bash
cd /mnt/c/Users/chris/hornelore
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
bash scripts/stop_all.sh

PRESERVE=/mnt/<preservation-drive>/hornelore_laptop_preservation/$(date +%Y%m%d)

du -sh "$ROOT"                       # need this much, plus headroom
df -h "$(dirname "$PRESERVE")"       # confirm it fits
mkdir -p "$PRESERVE"

printf 'PRESERVE=%q\n' "$PRESERVE" >> /mnt/c/lorevox_packages/laptop-rebuild-session.env

rsync -a --info=progress2 "$ROOT/" "$PRESERVE/"
sync
```

Verify — every line must agree:

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
echo "SOURCE files: $(find "$ROOT" -type f | wc -l)"
echo "COPY   files: $(find "$PRESERVE" -type f | wc -l)"

sha256sum "$DB" "$PRESERVE/db/$DBNAME"          # the two hashes must match

rsync -a --checksum --dry-run --itemize-changes "$ROOT/" "$PRESERVE/"   # must print nothing

sqlite3 -readonly "$PRESERVE/db/$DBNAME" "PRAGMA integrity_check; SELECT COUNT(*) FROM people;"
```

Any disagreement is **HARD STOP 5**.

## 6 · Clean only actual split-root configuration

- **Keep** `DATA_DIR=/mnt/c/hornelore_data` and `DB_NAME=hornelore.sqlite3`.
- **Comment out** `UPLOADS_DIR` and `MEDIA_DIR` — both default under `DATA_DIR`
  (`HANDOFF.md:93`). The gate does not catch a split here.
- **Leave** `TTS_HOME`. Leave `FAISS_PATH`.
- `HORNELORE_DATA_DIR` / `DB_PATH` are **absent from the laptop `.env`** — nothing to remove.
- `AUTHORS_DIR` / `KNOWLEDGE_DIR` are not gate inputs; leave them unless the gate names them.

```bash
cd /mnt/c/Users/chris/hornelore
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
cp -a .env ".env.pre_laptop_rebuild_$(date +%Y%m%d-%H%M%S)"

sed -i -E \
  -e 's|^UPLOADS_DIR=.*$|# Laptop rebuild: UPLOADS_DIR defaults to DATA_DIR/uploads|' \
  -e 's|^MEDIA_DIR=.*$|# Laptop rebuild: MEDIA_DIR defaults to DATA_DIR/media|' \
  .env

grep -nE '^(DATA_DIR|DB_NAME|UPLOADS_DIR|MEDIA_DIR|TTS_HOME|FAISS_PATH)=' .env
```

`DATA_DIR`, `DB_NAME`, `TTS_HOME` and `FAISS_PATH` must still be present; `UPLOADS_DIR` and
`MEDIA_DIR` must be gone. **Then re-run the gate and require `problems: []` again** — the
edit could have introduced a split root, and this is the only check that catches it:

```bash
cd /mnt/c/Users/chris/hornelore
(
  unset DATA_DIR DB_NAME HORNELORE_DATA_DIR DB_PATH UPLOADS_DIR MEDIA_DIR
  set -a; source .env; set +a
  PYTHONPATH=server/code .venv/bin/python -c \
    "from api import runtime_root as r; import json; print(json.dumps(r.describe_root(), indent=2))"
)
```

## 7 · Start and prove the world

```bash
cd /mnt/c/Users/chris/hornelore
unset DATA_DIR DB_NAME HORNELORE_DATA_DIR DB_PATH UPLOADS_DIR MEDIA_DIR
bash scripts/start_all.sh
```

No unexpected `DATA_DIR from caller …` in the banner. Then:

```bash
grep -F "Lorevox runtime root:" .runtime/logs/api.log | tail -1
curl -s 'http://127.0.0.1:8000/api/people?include_deleted=true&limit=1000' | python3 -m json.tool
```

## 8 · Fresh-export the three

Fresh, **not** the existing packages — those are stale relative to whatever has been added
since (`HANDOFF.md:99`).

```bash
cd /mnt/c/Users/chris/hornelore
source /mnt/c/lorevox_packages/laptop-rebuild-session.env

RUN="$(date +%Y%m%d-%H%M%S)"
OUT="/mnt/c/lorevox_packages/laptop-fresh-$RUN"
mkdir -p "$OUT"

printf 'RUN=%q\nOUT=%q\n' "$RUN" "$OUT" >> /mnt/c/lorevox_packages/laptop-rebuild-session.env
cat /mnt/c/lorevox_packages/laptop-rebuild-session.env
```

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
cd /mnt/c/Users/chris/hornelore
for ID in a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2 \
          4aa0cc2b-1f27-433a-9152-203bb1f69a55 \
          93479171-0b97-4072-bcf0-d44c7f9078ba; do
  PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py export \
    --narrator "$ID" --data-dir "$ROOT" --db "$DB" --out "$OUT" \
    | tee -a "$OUT/export.log"
done
```

## 9 · Validate, then DERIVE the contract from the manifests

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
cd /mnt/c/Users/chris/hornelore

N=$(ls -1 "$OUT"/*.lorevox.zip 2>/dev/null | wc -l)
[ "$N" -eq 3 ] || { echo "STOP: expected 3 packages, found $N"; exit 1; }

for p in "$OUT"/*.lorevox.zip; do
  echo "=== $p"
  PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py validate "$p" || exit 1
done
( cd "$OUT" && sha256sum *.lorevox.zip | tee SHA256SUMS.txt )
```

The contract is **read out of the packages**, never retyped from scrollback. Keys verified
against `services/narrator_package.py`: `MANIFEST_NAME` line 82, `package_id` 808,
`narrator_id` 811, `source_commit` 814, `record_counts_by_lane` 823, `file_counts_by_lane`
824, `bytes_by_lane` 1079; the ZIP stores paths relative to the bag root (862-864), so the
manifest sits at the archive root.

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
cd /mnt/c/Users/chris/hornelore
python3 - "$OUT" <<'PY'
import json, sys, zipfile
from pathlib import Path

out = Path(sys.argv[1])
wanted = {
    "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2": "CHRIS",
    "4aa0cc2b-1f27-433a-9152-203bb1f69a55": "KENT",
    "93479171-0b97-4072-bcf0-d44c7f9078ba": "JANICE",
}
REFERENCE = {"CHRIS": (524, 214), "KENT": (43, 45), "JANICE": (66, 21)}

pkgs = sorted(out.glob("*.lorevox.zip"))
if len(pkgs) != 3:
    raise SystemExit(f"STOP: expected exactly 3 packages in {out}, found {len(pkgs)}: "
                     f"{[p.name for p in pkgs]}")

found, files_total, bytes_total = {}, 0, 0
for pkg in pkgs:
    with zipfile.ZipFile(pkg) as z:
        with z.open("lorevox-manifest.json") as f:
            m = json.load(f)
    pid = m["narrator_id"]
    # An unexpected narrator in this directory is a STOP, never a skip: it means
    # the export wrote somewhere unintended, or a stale package is present.
    if pid not in wanted:
        raise SystemExit(f"STOP: {pkg.name} carries unexpected narrator {pid}")
    # Two packages for one narrator must never be silently collapsed — the
    # second would overwrite the first and the contract would be arbitrary.
    if pid in found:
        raise SystemExit(f"STOP: duplicate package for {wanted[pid]} ({pid}): "
                         f"{found[pid]['package']} and {pkg.name}")
    rows  = sum(int(v) for v in m["record_counts_by_lane"].values())
    files = sum(int(v) for v in m["file_counts_by_lane"].values())
    nbyte = sum(int(v) for v in (m.get("bytes_by_lane") or {}).values())
    found[pid] = dict(label=wanted[pid], rows=rows, files=files, bytes=nbyte,
                      package_id=m["package_id"], package=pkg.name,
                      source_commit=m["source_commit"])
    files_total += files
    bytes_total += nbyte

missing = set(wanted) - set(found)
if missing:
    raise SystemExit(f"STOP: missing fresh packages for {sorted(missing)}")
assert len(found) == 3, f"STOP: {len(found)} narrators resolved, expected 3"

lines = []
for pid, label in wanted.items():
    x = found[pid]
    lines += [f"{label}_ID={pid}",
              f"{label}_ROWS={x['rows']}",
              f"{label}_FILES={x['files']}",
              f"{label}_BYTES={x['bytes']}",
              f"{label}_PACKAGE_ID={x['package_id']}",
              f"{label}_PACKAGE={x['package']}",
              f"{label}_SOURCE_COMMIT={x['source_commit']}"]
lines += [f"FILES_TOTAL={files_total}", f"BYTES_TOTAL={bytes_total}"]

path = out / "rebuild-contract.txt"
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(path.read_text())

print("--- SANITY vs the 2026-09-12/14 reference (NOT an acceptance test) ---")
for pid, label in wanted.items():
    x = found[pid]
    r_rows, r_files = REFERENCE[label]
    print(f"{label:8} rows {x['rows']:>5} (ref {r_rows:>4}, {x['rows']-r_rows:+d})   "
          f"files {x['files']:>4} (ref {r_files:>4}, {x['files']-r_files:+d})")
print(f"{'TOTAL':8} files {files_total:>4} (ref  280, {files_total-280:+d})")
print("Growth is expected. A sharp CONTRACTION is HARD STOP 7 — investigate before deleting.")
PY
```

## 10 · Extra SQLite safety copy

Not the portable backup — a second escape hatch, created **before** the USB copy so it
travels with the packages.

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
sqlite3 "$DB" ".backup '$OUT/laptop-before-erasure.sqlite3'"
sqlite3 -readonly "$OUT/laptop-before-erasure.sqlite3" \
  "PRAGMA integrity_check; SELECT COUNT(*) FROM people;"

# The checksum file must carry a RELATIVE filename. With an absolute path in it,
# `sha256sum -c` run while standing on the USB would follow the path back to the
# laptop original and report OK without ever reading the USB copy.
(
  cd "$OUT"
  sha256sum laptop-before-erasure.sqlite3 | tee laptop-before-erasure.sqlite3.sha256
)
```

## 11 · Copy to exFAT USB and verify FROM the USB

USB must be exFAT (`HANDOFF.md:100`) and **not** the preservation drive from step 5.

```bash
powershell.exe -NoProfile -Command \
  "Get-Volume | Where-Object DriveLetter | Format-Table DriveLetter,FileSystemLabel,FileSystem,SizeRemaining"
```

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
USBDEST="/mnt/<usb-letter>/Lorevox_Laptop_Fresh_$RUN"
mkdir -p "$USBDEST"
cp -av "$OUT/." "$USBDEST/"
sync

printf 'USBDEST=%q\n' "$USBDEST" >> /mnt/c/lorevox_packages/laptop-rebuild-session.env
cat /mnt/c/lorevox_packages/laptop-rebuild-session.env
```

Verify **standing on the USB**, so the checksums read USB bytes:

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
cd "$USBDEST"
sha256sum -c SHA256SUMS.txt                        # every line OK
sha256sum -c laptop-before-erasure.sqlite3.sha256  # OK

cd /mnt/c/Users/chris/hornelore
for p in "$USBDEST"/*.lorevox.zip; do
  PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py validate "$p" || exit 1
done
```

Copies now standing: **(1)** `$OUT` on the laptop disk · **(2)** USB · **(3)** full-root
preservation on a separate device.

## 12 · Freeze and CONSCIOUSLY review the erasure list

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
curl -s 'http://127.0.0.1:8000/api/people?include_deleted=true&limit=1000' \
  > "$OUT/people_before_erasure.json"

python3 - "$OUT/people_before_erasure.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
fam = {"a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
       "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
       "93479171-0b97-4072-bcf0-d44c7f9078ba"}
ppl = d.get("people", [])
for p in ppl:
    print(("FAMILY " if p["id"] in fam else "       "), p["id"], p.get("display_name", ""))
print(f"\nTOTAL {len(ppl)}   family {sum(1 for p in ppl if p['id'] in fam)}"
      f"   OTHER {sum(1 for p in ppl if p['id'] not in fam)}")
PY

python3 - "$OUT/people_before_erasure.json" <<'PY' > "$OUT/ids_to_erase.txt"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
for p in d.get("people", []):
    print(p["id"])
PY
```

> **READ THE LIST. Every narrator on it is about to be permanently erased, and only three
> of them have portable packages.** The other ~71 exist solely inside the step-5
> preservation copy. This is a decision, not a formality — **HARD STOP 10** until it is
> consciously authorized.

## 13 · Hard-erase

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
cd /mnt/c/Users/chris/hornelore

while read -r ID; do
  [ -n "$ID" ] || continue
  BODY="/tmp/erase-$ID.json"
  CODE=$(curl -sS -o "$BODY" -w '%{http_code}' -X DELETE \
    "http://127.0.0.1:8000/api/people/$ID?mode=hard")
  echo; echo "=== $ID HTTP $CODE ==="; cat "$BODY"; echo

  if [ "$CODE" = "207" ]; then
    echo "Partial — running the saved-plan retry."
    CODE2=$(curl -sS -o "$BODY.retry" -w '%{http_code}' -X POST \
      "http://127.0.0.1:8000/api/people/$ID/erase-retry")
    echo "RETRY HTTP $CODE2"; cat "$BODY.retry"; echo
    [ "$CODE2" = "200" ] || { echo "STOP: erasure incomplete for $ID"; exit 1; }
  elif [ "$CODE" != "200" ]; then
    echo "STOP: hard deletion failed for $ID"; exit 1
  fi
done < "$OUT/ids_to_erase.txt"
```

**207 is not success.** The router distinguishes a complete hard deletion from a partial one
(`routers/people.py:303,313`). The retry route is **`erase-retry`** — see correction 1.

## 14 · Prove empty, then prove nothing re-seeds

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
curl -s 'http://127.0.0.1:8000/api/people?include_deleted=true&limit=1000' | python3 -m json.tool

PYTHONPATH=server/code .venv/bin/python scripts/family_root_verify.py \
  --data-dir "$ROOT" --db "$DB"

sqlite3 -readonly "$DB" "PRAGMA integrity_check; PRAGMA foreign_key_check; SELECT COUNT(*) FROM people;"
```

`people` must be zero. **A non-narrator remainder is EXPECTED and is not a defect**
(`HANDOFF.md:103`): `import_staging`, agent transcripts and the installation-local ledgers
are lane-keyed, not narrator-keyed. What matters: no narrator rows, no orphaned owners, FK
clean, no dangling semantic references.

Then prove the Phase 7 seeder removal really holds:

```bash
bash scripts/stop_all.sh
unset DATA_DIR DB_NAME HORNELORE_DATA_DIR DB_PATH UPLOADS_DIR MEDIA_DIR
bash scripts/start_all.sh
curl -s 'http://127.0.0.1:8000/api/people?include_deleted=true&limit=1000' | python3 -m json.tool
```

Still empty.

## 15 · Restore the three from USB

```bash
cd /mnt/c/Users/chris/hornelore
bash scripts/stop_all.sh
source /mnt/c/lorevox_packages/laptop-rebuild-session.env

CHRIS_PKG="$(find "$USBDEST" -maxdepth 1 -name 'Christopher*.lorevox.zip' -print -quit)"
KENT_PKG="$(find "$USBDEST" -maxdepth 1 -name 'Kent*.lorevox.zip' -print -quit)"
JANICE_PKG="$(find "$USBDEST" -maxdepth 1 -name 'Janice*.lorevox.zip' -print -quit)"
printf 'Christopher: %s\nKent: %s\nJanice: %s\n' "$CHRIS_PKG" "$KENT_PKG" "$JANICE_PKG"
```

None may be blank. Then, one at a time:

```bash
for PKG in "$CHRIS_PKG" "$KENT_PKG" "$JANICE_PKG"; do
  PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py restore \
    "$PKG" --data-dir "$ROOT" --db "$DB" --yes
done
```

## 16 · Verify exactly those three — ONE invocation

`--expect-rows` values come from `rebuild-contract.txt`, **not** from the historical
reference (correction 3).

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
source "$OUT/rebuild-contract.txt"

PYTHONPATH=server/code .venv/bin/python scripts/family_root_verify.py \
  --data-dir "$ROOT" --db "$DB" \
  --expect "$CHRIS_ID"  --expect "$KENT_ID"  --expect "$JANICE_ID" \
  --expect-rows "$CHRIS_ID=$CHRIS_ROWS" \
  --expect-rows "$KENT_ID=$KENT_ROWS" \
  --expect-rows "$JANICE_ID=$JANICE_ROWS"
```

Want `total: 3`, `--expect: 3 named, MATCHES`, `orphaned owners found: 0`,
`violations: 0`, `dangling references: 0`, `CLEAN`.

## 17 · Re-export, compare, finish

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
source "$OUT/rebuild-contract.txt"
POST="/mnt/c/lorevox_packages/laptop-postrestore-$RUN"
mkdir -p "$POST"

printf 'POST=%q\n' "$POST" >> /mnt/c/lorevox_packages/laptop-rebuild-session.env

for ID in "$CHRIS_ID" "$KENT_ID" "$JANICE_ID"; do
  PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py export \
    --narrator "$ID" --data-dir "$ROOT" --db "$DB" --out "$POST"
done

for N in Christopher Kent Janice; do
  PRE="$(find "$OUT"  -maxdepth 1 -name "$N*.lorevox.zip" -print -quit)"
  NEW="$(find "$POST" -maxdepth 1 -name "$N*.lorevox.zip" -print -quit)"
  echo "=== $N"
  PYTHONPATH=server/code .venv/bin/python scripts/narrator_package.py compare "$PRE" "$NEW"
done
```

All three **`EQUIVALENT`**; only the schema fingerprint may be informational.

Then **execute** the payload comparison — derive the post-restore total from the three new
manifests and require it to equal `FILES_TOTAL` from the fresh contract. This exits nonzero
on mismatch and prints both numbers:

```bash
source /mnt/c/lorevox_packages/laptop-rebuild-session.env
source "$OUT/rebuild-contract.txt"
cd /mnt/c/Users/chris/hornelore

python3 - "$POST" "$FILES_TOTAL" <<'PY' || { echo "STOP: payload totals disagree"; exit 1; }
import json, sys, zipfile
from pathlib import Path

post, expected = Path(sys.argv[1]), int(sys.argv[2])
pkgs = sorted(post.glob("*.lorevox.zip"))
if len(pkgs) != 3:
    raise SystemExit(f"STOP: expected 3 post-restore packages, found {len(pkgs)}")

total = 0
for pkg in pkgs:
    with zipfile.ZipFile(pkg) as z:
        with z.open("lorevox-manifest.json") as f:
            m = json.load(f)
    n = sum(int(v) for v in m["file_counts_by_lane"].values())
    print(f"{pkg.name}: {n} files")
    total += n

print(f"\npost-restore FILES_TOTAL = {total}")
print(f"fresh-export FILES_TOTAL = {expected}")
if total != expected:
    raise SystemExit(f"MISMATCH: {total} != {expected}")
print("payload totals MATCH")
PY
```

Then start normally:

```bash
cd /mnt/c/Users/chris/hornelore
unset DATA_DIR DB_NAME HORNELORE_DATA_DIR DB_PATH UPLOADS_DIR MEDIA_DIR
bash scripts/start_all.sh
grep -F "Lorevox runtime root:" .runtime/logs/api.log | tail -1
curl -s 'http://127.0.0.1:8000/api/people?include_deleted=true&limit=1000' | python3 -m json.tool
```

Exactly Christopher, Kent and Janice.

---

## Then the actual work — with one live bug in the way

**`BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01` is live and unfixed** (`HANDOFF.md:108,110`).
An ordinary Bio Builder save of a **spouse or child section drops `maidenName`,
`birthPlace`, `notes` and `relation`** that are already stored. It bites the moment family
editing starts. Known, owed, not blocking the rebuild — but do not discover it by losing data.

## Retention

**Do not delete anything yet** (`HANDOFF.md:61`). The step-5 preservation copy, the desktop
narrator copies, and the superseded packages all stay until the rebuilt laptop has been in
real use long enough to be trusted. Retirement is a separate, deliberate decision.
