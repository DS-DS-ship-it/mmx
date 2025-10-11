use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DoctorReport {
    pub ok: bool,
    pub hints: Vec<String>,
}

pub fn run_inspect() -> DoctorReport {
    DoctorReport { ok: true, hints: Vec::new() }
}
