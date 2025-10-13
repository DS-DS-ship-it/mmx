use std::path::Path;
use symphonia::core::formats::FormatReader;
use anyhow::Result;

pub fn write_mkv<R: FormatReader + 'static>(_format: R, output: &Path) -> Result<()> {
    println!("✅ Writing MKV to {:?}", output);
    // TODO: implement real MKV muxing here
    Ok(())
}

pub fn write_mp4<R: FormatReader + 'static>(_format: R, output: &Path) -> Result<()> {
    println!("✅ Writing MP4 to {:?}", output);
    // TODO: implement real MP4 muxing here
    Ok(())
}
