#!/usr/bin/env bash
set -euo pipefail

# ---- repo root ----
REPO_DIR="${MMX_REPO:-}"
if [[ -z "${REPO_DIR}" ]]; then
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_DIR="$(git rev-parse --show-toplevel)"
  else
    REPO_DIR="$HOME/mmx"
  fi
fi
cd "$REPO_DIR" || { echo "[fail] repo not found: $REPO_DIR"; exit 1; }
test -f mmx-cli/Cargo.toml || { echo "[fail] mmx-cli/Cargo.toml missing at $PWD"; exit 1; }
test -f mmx-core/Cargo.toml || { echo "[fail] mmx-core/Cargo.toml missing at $PWD"; exit 1; }

# ---- backups ----
cp -n mmx-cli/Cargo.toml mmx-cli/Cargo.toml.bak_fix 2>/dev/null || true
cp -n mmx-core/Cargo.toml mmx-core/Cargo.toml.bak_fix 2>/dev/null || true
cp -n mmx-core/src/backend.rs mmx-core/src/backend.rs.bak_fix 2>/dev/null || true

# ---- 1) mmx-cli/Cargo.toml: remove duplicate "[dependencies] # reopened ..." header lines ----
perl -0777 -pi -e 's/^\[dependencies\][^\n]*#\s*reopened[^\n]*\n//m' mmx-cli/Cargo.toml

# Keep only the first plain [dependencies] header line
awk '
  BEGIN{depcount=0}
  /^\[dependencies\][[:space:]]*$/ {
    depcount++
    if(depcount>1){ next }
  }
  { print }
' mmx-cli/Cargo.toml > mmx-cli/Cargo.toml.tmp && mv mmx-cli/Cargo.toml.tmp mmx-cli/Cargo.toml

# ---- 2) mmx-cli/Cargo.toml: fix broken clap inline table ----
perl -0777 -pi -e 's/^clap\s*=\s*\{[^}]*\}\s*$/clap = { version = "4", features = ["derive"] }\n/m' mmx-cli/Cargo.toml
if ! grep -Eq '^\s*clap\s*=' mmx-cli/Cargo.toml; then
  awk '
    BEGIN{inserted=0}
    {
      print
      if(!inserted && $0 ~ /^\[dependencies\][[:space:]]*$/){
        print "clap = { version = \"4\", features = [\"derive\"] }"
        inserted=1
      }
    }
    END{
      if(!inserted){
        print ""
        print "[dependencies]"
        print "clap = { version = \"4\", features = [\"derive\"] }"
      }
    }
  ' mmx-cli/Cargo.toml > mmx-cli/Cargo.toml.new && mv mmx-cli/Cargo.toml.new mmx-cli/Cargo.toml
fi

# ---- 3) mmx-core/Cargo.toml: ensure anyhow dependency ----
if ! grep -Eq '^\s*anyhow\s*=' mmx-core/Cargo.toml; then
  if grep -Eq '^\[dependencies\][[:space:]]*$' mmx-core/Cargo.toml; then
    awk '
      BEGIN{done=0}
      {
        print
        if(!done && $0 ~ /^\[dependencies\][[:space:]]*$/){
          print "anyhow = \"1\""
          done=1
        }
      }
      END{
        if(!done){
          print ""
          print "[dependencies]"
          print "anyhow = \"1\""
        }
      }
    ' mmx-core/Cargo.toml > mmx-core/Cargo.toml.new && mv mmx-core/Cargo.toml.new mmx-core/Cargo.toml
  else
    {
      echo ""
      echo "[dependencies]"
      echo 'anyhow = "1"'
    } >> mmx-core/Cargo.toml
  fi
fi

# ---- 4) mmx-core/src/backend.rs: add `use anyhow::anyhow;` if missing ----
if test -f mmx-core/src/backend.rs; then
  if ! grep -q 'use anyhow::anyhow;' mmx-core/src/backend.rs; then
    if grep -q '^use anyhow::Result;' mmx-core/src/backend.rs; then
      awk '
        BEGIN{done=0}
        {
          print
          if(!done && $0 ~ /^use anyhow::Result;/){
            print "use anyhow::anyhow;"
            done=1
          }
        }
        END{
          if(!done){
            print "use anyhow::anyhow;"
          }
        }
      ' mmx-core/src/backend.rs > mmx-core/src/backend.rs.new && mv mmx-core/src/backend.rs.new mmx-core/src/backend.rs
    else
      awk '
        BEGIN{ins=0}
        NR==1{
          print
          print "use anyhow::anyhow;"
          ins=1
          next
        }
        { print }
      ' mmx-core/src/backend.rs > mmx-core/src/backend.rs.new && mv mmx-core/src/backend.rs.new mmx-core/src/backend.rs
    fi
  fi
fi

# ---- 5) Build (GST feature on) ----
cargo build -p mmx-cli -F mmx-core/gst --release

echo "[ok] build complete: target/release/mmx"
