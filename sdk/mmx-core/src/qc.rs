use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct QcReport {
    pub psnr: Option<f64>,
    pub ssim: Option<f64>,
    pub vmaf: Option<f64>,
    pub details: String,
}
