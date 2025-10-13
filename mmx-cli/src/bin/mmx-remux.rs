use gstreamer as gst;
use gst::prelude::*;
use std::path::Path;

/// Choose a muxer based on output extension.
fn pick_muxer(ext: &str) -> &'static str {
    match ext {
        "mkv" | "matroska" => "matroskamux",
        "webm" => "webmmux",
        "mp4" | "m4v" | "m4a" | "mov" => "mp4mux",
        _ => "matroskamux",
    }
}

/// Optional parser to ensure the muxer gets the right bitstream caps.
fn parser_for_caps(struct_name: &str, caps: &gst::StructureRef) -> Option<&'static str> {
    match struct_name {
        "video/x-h264" => Some("h264parse"),
        "video/x-h265" => Some("h265parse"),
        "audio/mpeg" => {
            if let Ok(v) = caps.get::<i32>("mpegversion") {
                match v {
                    4 => Some("aacparse"),
                    1 | 2 => Some("mp3parse"),
                    _ => None,
                }
            } else {
                None
            }
        }
        "audio/x-ac3" => Some("ac3parse"),
        "audio/x-eac3" => Some("eac3parse"),
        "audio/x-opus" => Some("opusparse"),
        "audio/x-vorbis" => Some("vorbisparse"),
        _ => None,
    }
}

/// Map caps to a requested pad template on muxer.
fn mux_pad_template_for(struct_name: &str) -> Option<&'static str> {
    if struct_name.starts_with("video/") {
        Some("video_%u")
    } else if struct_name.starts_with("audio/") {
        Some("audio_%u")
    } else if struct_name.starts_with("subtitle/") || struct_name.starts_with("text/") {
        Some("subtitle_%u")
    } else {
        None
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    gst::init()?;

    let mut argv = std::env::args().skip(1).collect::<Vec<_>>();
    if argv.len() != 2 {
        eprintln!("usage: mmx-remux <input> <output>");
        std::process::exit(2);
    }
    let input = argv.remove(0);
    let output = argv.remove(0);

    let ext = Path::new(&output)
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    let muxer_name = pick_muxer(&ext);

    eprintln!("🔎 Input:  {input}");
    eprintln!("🧩 Muxer:  {muxer_name}");
    eprintln!("🎯 Output: {output}");

    let pipeline = gst::Pipeline::new(); // ✅ 0.24 API: no args

    let filesrc = gst::ElementFactory::make("filesrc")
        .property("location", &input)
        .build()?;

    // For now, target MP4/MOV inputs with qtdemux (most common case).
    // You can add more demuxers (matroskademux, oggdemux, etc.) as needed.
    let demux = gst::ElementFactory::make("qtdemux").name("demux").build()?;

    let mux = gst::ElementFactory::make(muxer_name).name("mux").build()?;
    let sink = gst::ElementFactory::make("filesink")
        .property("location", &output)
        .property("sync", false)
        .build()?;

    pipeline.add_many(&[&filesrc, &demux, &mux, &sink])?;
    filesrc.link(&demux)?;
    mux.link(&sink)?;

    // Handle dynamic pads from demuxer.
    let pipeline_weak = pipeline.downgrade();
    let mux_weak = mux.downgrade();
    demux.connect_pad_added(move |_demuxer, src_pad| {
        let Some(pipeline) = pipeline_weak.upgrade() else { return };
        let Some(mux) = mux_weak.upgrade() else { return };

        // ✅ 0.24 fix: wrap query_caps(None) in Some(...) to match Option<Caps>
        let caps = src_pad
            .current_caps()
            .or_else(|| Some(src_pad.query_caps(None)));

        let Some(caps) = caps else {
            eprintln!("⚠️  No caps on new pad; skipping.");
            return;
        };
        let Some(s) = caps.structure(0) else {
            eprintln!("⚠️  No structure in caps; skipping.");
            return;
        };
        let st_name = s.name().to_string();

        // Pick muxer pad template.
        let Some(req_tmpl) = mux_pad_template_for(&st_name) else {
            eprintln!("⚠️  Unsupported stream caps: {st_name}");
            return;
        };

        // Build chain: src_pad -> queue -> [parser?] -> mux(requested sink pad)
        let queue = match gst::ElementFactory::make("queue").build() {
            Ok(q) => q,
            Err(e) => {
                eprintln!("⚠️  Failed to create queue: {e:?}");
                return;
            }
        };

        let parser_name = parser_for_caps(&st_name, s);
        let parser = parser_name.and_then(|name| {
            gst::ElementFactory::make(name).build().ok()
        });

        let mut to_add: Vec<&gst::Element> = vec![&queue];
        if let Some(ref p) = parser {
            to_add.push(p);
        }
        if let Err(e) = pipeline.add_many(&to_add) {
            eprintln!("⚠️  add_many failed: {e:?}");
            return;
        }
        for e in &to_add {
            let _ = e.sync_state_with_parent();
        }

        // Link the chain.
        if let Err(e) = src_pad.link(&queue.static_pad("sink").unwrap()) {
            eprintln!("⚠️  Could not link demux→queue: {e:?}");
            let _ = pipeline.remove(&queue);
            if let Some(p) = &parser { let _ = pipeline.remove(p); }
            return;
        }

        let upstream = if let Some(ref p) = parser {
            if let Err(e) = queue.link(p) {
                eprintln!("⚠️  Could not link queue→parser: {e:?}");
                return;
            }
            p
        } else {
            &queue
        };

        let Some(muxpad) = mux.request_pad_simple(req_tmpl) else {
            eprintln!("⚠️  Muxer refused pad template {req_tmpl}");
            return;
        };

        if let Err(e) = upstream.static_pad("src").unwrap().link(&muxpad) {
            eprintln!("⚠️  Could not link to mux: {e:?}");
        } else {
            eprintln!("🔗 Linked {st_name} → {req_tmpl} (parser: {})",
                parser_name.unwrap_or("none"));
        }
    });

    pipeline.set_state(gst::State::Playing)?;

    // Wait for EOS / Error
    let bus = pipeline.bus().expect("no bus");
    use gst::MessageView as MV;
    loop {
        match bus.timed_pop(None) {
            Some(msg) => match msg.view() {
                MV::Eos(..) => {
                    eprintln!("✅ Done.");
                    break;
                }
                MV::Error(e) => {
                    eprintln!("❌ GStreamer error: {} (debug: {:?})", e.error(), e.debug());
                    std::process::exit(1);
                }
                _ => {}
            },
            None => break,
        }
    }

    pipeline.set_state(gst::State::Null)?;
    Ok(())
}
