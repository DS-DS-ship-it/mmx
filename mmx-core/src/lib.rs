use std::path::Path;
use anyhow::Result;
use symphonia::core::formats::FormatReader;

pub fn write_mp4<R: FormatReader + 'static>(_reader: R, _output: &Path) -> Result<()> {
    println!("🔧 Writing MP4 container (stub — implement me)");
    Ok(())
}

pub fn write_mkv<R: FormatReader + 'static>(_reader: R, _output: &Path) -> Result<()> {
    println!("🔧 Writing MKV container (stub — implement me)");
    Ok(())
}
