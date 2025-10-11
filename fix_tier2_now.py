from pathlib import Path
import re
import textwrap

root = Path(".")

core_toml   = root/"mmx-core/Cargo.toml"
cli_toml    = root/"mmx-cli/Cargo.toml"
cli_main    = root/"mmx-cli/src/main.rs"

# --- A) Ensure mmx-core has regex + serde + serde_json + which ---
ct = core_toml.read_text()
if "[dependencies]" not in ct:
    ct += "\n[dependencies]\n"

def ensure_dep(toml: str, line: str) -> str:
    name = line.split("=", 1)[0].strip()
    if re.search(rf"(?m)^\s*{re.escape(name)}\b", toml) is None:
        toml += line + "\n"
    return toml

ct = ensure_dep(ct, 'serde = { version = "1", features = ["derive"] }')
ct = ensure_dep(ct, 'serde_json = "1"')
ct = ensure_dep(ct, 'which = "6"')
ct = ensure_dep(ct, 'regex = "1"')  # <-- missing crate causing E0433
core_toml.write_text(ct)

# --- B) CLI: ensure we depend on serde_json/regex/which (harmless if already present) ---
tt = cli_toml.read_text()
if "[dependencies]" not in tt:
    tt += "\n[dependencies]\n"
for dep in ['serde_json = "1"', 'regex = "1"', 'which = "6"']:
    name = dep.split("=",1)[0].strip()
    if re.search(rf"(?m)^\s*{re.escape(name)}\b", tt) is None:
        tt += dep + "\n"
cli_toml.write_text(tt)

# --- C) CLI: replace PackArgs and cmd_pack with Tier-2 flags + unified call ---
ms = cli_main.read_text()

# 1) make sure we can use the packager APIs
if "use mmx_core::packager" not in ms:
    ms = re.sub(r'(use\s+mmx_core::backend[^\n]*;)', r'\1\nuse mmx_core::packager;', ms, count=1)
if "use mmx_core::ladder" not in ms:
    ms = re.sub(r'(use\s+mmx_core::backend[^\n]*;)', r'\1\nuse mmx_core::ladder;', ms, count=1)

# 2) replace PackArgs block with extended flags
packargs_re = re.compile(r"(?s)#[^\n]*derive[^\n]*\n\s*pub\s+struct\s+PackArgs\s*\{.*?\}")
new_packargs = textwrap.dedent(r'''
    #[derive(clap::Args, Debug, Clone)]
    pub struct PackArgs {
        /// Input media file
        #[arg(long)]
        input: String,

        /// Packager kind: hls|dash
        #[arg(long, default_value = "hls")]
        packager: String,

        /// HLS output directory (required if --packager hls)
        #[arg(long = "hls-out")]
        hls_out: Option<String>,

        /// DASH output directory (required if --packager dash)
        #[arg(long = "dash-out")]
        dash_out: Option<String>,

        /// Segment duration (seconds)
        #[arg(long = "segment-duration", default_value_t = 4)]
        segment_duration: u32,

        /// Build ladder automatically from source dimensions
        #[arg(long = "auto-ladder", default_value_t = True)]
        auto_ladder: bool,

        /// Manual ladder spec (e.g., "426x240@400k,640x360@800k,1280x720@2500k")
        #[arg(long = "ladder")]
        ladder: Option<String>,

        /// Force keyframes at scene cuts (per-shot)
        #[arg(long = "per-shot", default_value_t = False)]
        per_shot: bool,

        /// Tone-map preset: auto|off|reinhard|hable|mobius
        #[arg(long = "tone-map", default_value = "auto")]
        tone_map: String,
    }
''').replace("True","true").replace("False","false")

if packargs_re.search(ms):
    ms = packargs_re.sub(new_packargs, ms, count=1)
else:
    # append near top if for some reason PackArgs is missing
    ms = ms.replace("pub enum Command", new_packargs + "\n\npub enum Command")

# 3) replace cmd_pack with unified pack call
cmdpack_re = re.compile(r"(?s)fn\s+cmd_pack\s*\([^\)]*\)\s*->\s*anyhow::Result<\(\)>\s*\{.*?\}\s*")
new_cmdpack = textwrap.dedent(r'''
    fn cmd_pack(a: PackArgs) -> anyhow::Result<()> {
        use mmx_core::packager::PackKind;
        let kind = match a.packager.as_str() {
            "hls" => PackKind::Hls,
            "dash" => PackKind::Dash,
            other => anyhow::bail!("unknown --packager {}", other),
        };
        let out = match kind {
            PackKind::Hls => a.hls_out.ok_or_else(|| anyhow::anyhow!("--hls-out is required for HLS"))?,
            PackKind::Dash => a.dash_out.ok_or_else(|| anyhow::anyhow!("--dash-out is required for DASH"))?,
        };
        mmx_core::packager::pack_unified_auto(
            kind,
            std::path::Path::new(&a.input),
            std::path::Path::new(&out),
            a.segment_duration,
            a.auto_ladder,
            a.ladder.as_deref(),
            a.per_shot,
            &a.tone_map,
        )?;
        eprintln!("[pack] wrote to {}", out);
        Ok(())
    }
''')

if cmdpack_re.search(ms):
    ms = cmdpack_re.sub(new_cmdpack, ms, count=1)
else:
    # if missing, append just before main()
    ms = re.sub(r"fn\s+main\s*\(", new_cmdpack + "\n\nfn main(", ms, count=1)

# 4) Make sure the enum Command includes Pack(PackArgs) and match arms include it
if re.search(r"enum\s+Command\s*\{", ms) and "Pack(" not in ms:
    ms = re.sub(r"(enum\s+Command\s*\{\s*)", r"\1\n    Pack(PackArgs),", ms, count=1)
if "Command::Pack(" not in ms:
    ms = re.sub(r"(match\s+cli\.cmd\s*\{\s*)", r"\1\n        Command::Pack(a) => cmd_pack(a)?,", ms, count=1)

cli_main.write_text(ms)

print("[ok] core: added regex; cli: extended pack flags + unified pack call wired")
