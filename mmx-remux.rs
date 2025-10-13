derekwardlaw@Dereks-MacBook-Air mmx % cargo build --bin mmx-remux
./target/debug/mmx-remux input.mp4 output.mkv
   Compiling mmx-cli v0.2.0 (/Users/derekwardlaw/mmx/mmx-cli)
error[E0599]: no function or associated item named `new` found for struct `symphonia::symphonia_core::meta::Metadata` in the current scope
  --> mmx-cli/src/bin/mmx-remux.rs:30:24
   |
30 |         &mut Metadata::new()
   |                        ^^^ function or associated item not found in `symphonia::symphonia_core::meta::Metadata<'_>`

error[E0599]: no method named `downcast` found for struct `Box<dyn FormatReader>` in the current scope
  --> mmx-cli/src/bin/mmx-remux.rs:35:38
   |
35 |     if let Some(mp4_reader) = format.downcast::<IsoMp4Reader>().ok() {
   |                                      ^^^^^^^^ method not found in `Box<dyn FormatReader>`
   |
   = note: the method was found for
           - `Box<(dyn Any + 'static), A>`
           - `Box<(dyn Any + Send + 'static), A>`
           - `Box<(dyn Any + Send + Sync + 'static), A>`

error[E0599]: no method named `downcast` found for struct `Box<dyn FormatReader>` in the current scope
  --> mmx-cli/src/bin/mmx-remux.rs:37:45
   |
37 |     } else if let Some(mkv_reader) = format.downcast::<MkvReader>().ok() {
   |                                             ^^^^^^^^ method not found in `Box<dyn FormatReader>`
   |
   = note: the method was found for
           - `Box<(dyn Any + 'static), A>`
           - `Box<(dyn Any + Send + 'static), A>`
           - `Box<(dyn Any + Send + Sync + 'static), A>`

For more information about this error, try `rustc --explain E0599`.
error: could not compile `mmx-cli` (bin "mmx-remux") due to 3 previous errors
ffmpeg version 8.0 Copyright (c) 2000-2025 the FFmpeg developers
  built with Apple clang version 17.0.0 (clang-1700.0.13.3)
  configuration: --prefix=/opt/homebrew/Cellar/ffmpeg/8.0_1 --enable-shared --enable-pthreads --enable-version3 --cc=clang --host-cflags= --host-ldflags='-Wl,-ld_classic' --enable-ffplay --enable-gnutls --enable-gpl --enable-libaom --enable-libaribb24 --enable-libbluray --enable-libdav1d --enable-libharfbuzz --enable-libjxl --enable-libmp3lame --enable-libopus --enable-librav1e --enable-librist --enable-librubberband --enable-libsnappy --enable-libsrt --enable-libssh --enable-libsvtav1 --enable-libtesseract --enable-libtheora --enable-libvidstab --enable-libvmaf --enable-libvorbis --enable-libvpx --enable-libwebp --enable-libx264 --enable-libx265 --enable-libxml2 --enable-libxvid --enable-lzma --enable-libfontconfig --enable-libfreetype --enable-frei0r --enable-libass --enable-libopencore-amrnb --enable-libopencore-amrwb --enable-libopenjpeg --enable-libspeex --enable-libsoxr --enable-libzmq --enable-libzimg --disable-libjack --disable-indev=jack --enable-videotoolbox --enable-audiotoolbox --enable-neon
  libavutil      60.  8.100 / 60.  8.100
  libavcodec     62. 11.100 / 62. 11.100
  libavformat    62.  3.100 / 62.  3.100
  libavdevice    62.  1.100 / 62.  1.100
  libavfilter    11.  4.100 / 11.  4.100
  libswscale      9.  1.100 /  9.  1.100
  libswresample   6.  1.100 /  6.  1.100
[mov,mp4,m4a,3gp,3g2,mj2 @ 0x11fe06560] Format mov,mp4,m4a,3gp,3g2,mj2 detected only with low score of 1, misdetection possible!
[mov,mp4,m4a,3gp,3g2,mj2 @ 0x11fe06560] moov atom not found
[in#0 @ 0x11fe04300] Error opening input: Invalid data found when processing input
Error opening input file input.mp4.
Error opening input files: Invalid data found when processing input
❌ ffmpeg exited with status: exit status: 183
derekwardlaw@Dereks-MacBook-Air mmx % >....                                     
# Add Symphonia dependencies to both
for PKG in "$CORE" "$CLI"; do
  cargo add symphonia --package symphonia --features="mp4,mkv" --manifest-path "$PKG/Cargo.toml"
done

# Add binary section to mmx-cli
if ! grep -q 'name = "mmx-remux"' "$CLI/Cargo.toml"; then
cat <<EOF >> "$CLI/Cargo.toml"

[[bin]]
name = "mmx-remux"
path = "src/bin/mmx-remux.rs"
EOF
fi

mkdir -p "$CLI/src/bin"
cat <<EOF > "$CLI/src/bin/mmx-remux.rs"
// (Paste the Rust code from above here)
EOF

echo "✅ Done! Now run: cd $CLI && cargo run --bin mmx-remux -- input.mp4 output.mkv"
zsh: event not found: /bin/bash
derekwardlaw@Dereks-MacBook-Air mmx % nano x14
derekwardlaw@Dereks-MacBook-Air mmx % ./x14
zsh: permission denied: ./x14
derekwardlaw@Dereks-MacBook-Air mmx % ~x14
zsh: no such user or named directory: x14
