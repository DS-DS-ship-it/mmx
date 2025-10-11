# quick_fix_tier0.sh
# usage: bash quick_fix_tier0.sh

set -euo pipefail

CLI="mmx-cli/src/main.rs"
GST="mmx-core/src/backend_gst.rs"

echo "[1/4] Ensure PathBuf import in $CLI"
if ! grep -q 'use std::path::PathBuf;' "$CLI"; then
  # insert PathBuf after the last top-level 'use ...;' line
  awk '
    BEGIN{added=0}
    {
      print $0
      if ($0 ~ /^use [^;]+;/) last=NR
      lines[NR]=$0
    }
    END{
      for(i=1;i<=NR;i++) print lines[i]
    }' "$CLI" >/tmp/cli.tmp

  # safer insert: put it after the first `use` line
  awk '
    BEGIN{inserted=0}
    {
      if (!inserted && $0 ~ /^use /) { print; print "use std::path::PathBuf;"; inserted=1; next }
      print
    }' /tmp/cli.tmp > /tmp/cli2.tmp

  mv /tmp/cli2.tmp "$CLI"
  rm -f /tmp/cli.tmp
  echo "  -> added 'use std::path::PathBuf;'"
else
  echo "  -> already present"
fi

echo "[2/4] Normalize RunArgs: remove ghost fields and wire manifest/progress_json (types safe)"
# Drop any ghost graph fields (harmless if not present)
sed -i '' -e '/^\s*graph_json\s*:/d' -e '/^\s*graph\s*:/d' "$CLI"

# Make sure RunArgs has manifest: Option<PathBuf> and progress_json: bool
# (append if missing; idempotent)
if ! grep -q 'struct RunArgs' "$CLI"; then
  echo "  -> NOTE: RunArgs block not found; skipping struct edits (likely customized already)"
else
  # Ensure a manifest field of PathBuf exists (remove a String one if found)
  sed -i '' -e 's/^\(\s*manifest\s*:\s*Option<\)String\(>\s*,\s*$\)/\1PathBuf\2/' "$CLI"
  if ! grep -q 'manifest:\s*Option<PathBuf>' "$CLI"; then
    # append just before the closing brace of struct RunArgs
    awk '
      BEGIN{inStruct=0}
      /struct[[:space:]]+RunArgs[[:space:]]*\{/ {inStruct=1}
      {print}
      inStruct && /\}/ && !printed {
        print "    #[arg(long = \"manifest\")]"
        print "    manifest: Option<PathBuf>,"
        print "    #[arg(long = \"progress-json\", default_value_t = false)]"
        print "    progress_json: bool,"
        printed=1
        inStruct=0
      }
    ' "$CLI" > /tmp/cli3.tmp && mv /tmp/cli3.tmp "$CLI"
    echo "  -> appended manifest/progress_json to RunArgs"
  else
    # ensure progress_json exists
    if ! grep -q 'progress_json:\s*bool' "$CLI"; then
      awk '
        BEGIN{inStruct=0}
        /struct[[:space:]]+RunArgs[[:space:]]*\{/ {inStruct=1}
        {print}
        inStruct && /\}/ && !printed {
          print "    #[arg(long = \"progress-json\", default_value_t = false)]"
          print "    progress_json: bool,"
          printed=1
          inStruct=0
        }
      ' "$CLI" > /tmp/cli4.tmp && mv /tmp/cli4.tmp "$CLI"
      echo "  -> appended progress_json to RunArgs"
    else
      echo "  -> RunArgs already has manifest/progress_json"
    end
  fi
fi

echo "[3/4] Wire cmd_run: assign manifest/progress_json and keep backend=a.backend"
# Remove any weird match on backend enum and just pass through a.backend (string)
perl -0777 -pe 's/opts\.backend\s*=\s*match\s*a\.backend\s*\{.*?\};/opts.backend = a.backend;/s' -i '' "$CLI" || true

# Ensure the assignments exist after opts.execute
if ! grep -q 'opts.manifest = a.manifest;' "$CLI"; then
  perl -0777 -pe 's/(opts\.execute\s*=\s*a\.execute\s*;\s*)/\1opts.manifest = a.manifest;\n/s' -i '' "$CLI"
  echo "  -> wired opts.manifest"
fi
if ! grep -q 'opts.progress_json = a.progress_json;' "$CLI"; then
  perl -0777 -pe 's/(opts\.manifest\s*=\s*a\.manifest\s*;\s*)/\1opts.progress_json = a.progress_json;\n/s' -i '' "$CLI"
  echo "  -> wired opts.progress_json"
fi

echo "[4/4] Fix GST: normalize opts param name and query_duration in $GST"
# a) rename parameter to `opts` in run(&self, ...) and build_pipeline_string(...)
perl -0777 -pe 's/(fn\s+run\s*\(\s*&self\s*,\s*)\w+(\s*:\s*&\s*RunOptions)/\1opts\2/s' -i '' "$GST"
perl -0777 -pe 's/(fn\s+build_pipeline_string\s*\(\s*)\w+(\s*:\s*&\s*RunOptions)/\1opts\2/s' -i '' "$GST"

# b) replace aliases with opts (run_opts, run_run_opts)
sed -i '' -e 's/\brun_run_opts\./opts./g' -e 's/\brun_opts\./opts./g' "$GST"

# c) drop duplicate imports of RunOptions (keep first)
# remove repeated single-line duplicates
awk '!seen[$0]++' "$GST" > /tmp/gst.tmp && mv /tmp/gst.tmp "$GST"

# d) query_duration: Result->Option and assign to Some(...)
sed -i '' \
  -e 's/if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()/if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()/' \
  -e 's/duration_ns = dur.map(|d| d.nseconds() as u128);/duration_ns = Some(dur.nseconds() as u128);/' \
  "$GST"

echo "Done. Now build:"
echo "  cargo build"
echo "  cargo build -p mmx-cli -F mmx-core/gst"
