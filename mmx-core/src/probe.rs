use serde::{Serialize, Deserialize};

pub const PROBE_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FormatInfo {
    pub container: Option<String>,
    pub duration_ns: Option<u128>,
    pub size: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum StreamKind { Video, Audio, Subtitle, Data, Unknown }
impl Default for StreamKind { fn default() -> Self { StreamKind::Unknown } }

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct StreamInfo {
    pub kind: StreamKind,
    pub codec: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub fps: Option<f64>,
    pub channels: Option<u32>,
    pub sample_rate: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Chapter {
    pub start_ns: u128,
    pub end_ns: u128,
    pub title: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProbeReport {
    pub schema_version: u32,
    pub path: String,
    pub format: FormatInfo,
    pub streams: Vec<StreamInfo>,
    pub chapters: Vec<Chapter>,
}

pub fn cheap_probe(path: &str) -> anyhow::Result<ProbeReport> {
    let size = std::fs::metadata(path).ok().map(|m| m.len());
    Ok(ProbeReport{
        schema_version: PROBE_SCHEMA_VERSION,
        path: path.to_string(),
        format: FormatInfo { container: None, duration_ns: None, size },
        streams: Vec::new(),
        chapters: Vec::new(),
    })
}
