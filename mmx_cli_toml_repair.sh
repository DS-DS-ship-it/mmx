#!/usr/bin/env bash
set -euo pipefail

test -f mmx-cli/Cargo.toml || { echo "[fail] mmx-cli/Cargo.toml missing"; exit 1; }

cp -n mmx-cli/Cargo.toml mmx-cli/Cargo.toml.bak_cli_fix 2>/dev/null || true

# Drop any "[dependencies] # reopened ..." headers that can confuse tooling
perl -0777 -pi -e 's/^\[dependencies\][^\n]*#\s*reopened[^\n]*\n//mg' mmx-cli/Cargo.toml

# Rebuild the dependencies section to ensure a single, valid clap line
awk '
  BEGIN{dep=0; wrote_clap=0}
  /^\[dependencies\][[:space:]]*$/ {
       print
       if(!wrote_clap){
         print "clap = { version = \"4\", features = [\"derive\"] }"
         wrote_clap=1
       }
       dep=1
       next
  }
  dep==1 && $0 ~ /^[[:space:]]*clap[[:space:]]*=/ { next }   # drop any existing clap lines in deps
  { print }
  END{
     if(!wrote_clap){
       print ""
       print "[dependencies]"
       print "clap = { version = \"4\", features = [\"derive\"] }"
     }
  }
' mmx-cli/Cargo.toml > mmx-cli/Cargo.toml.tmp && mv mmx-cli/Cargo.toml.tmp mmx-cli/Cargo.toml
