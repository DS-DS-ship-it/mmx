
// 0BSD
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LadderItem {
    pub w: u32,
    pub h: u32,
    /// video bitrate in kbps
    pub v_bitrate_k: u32,
    /// audio bitrate in kbps (per-variant; 0 means shared audio later)
    pub a_bitrate_k: u32,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Ladder {
    pub items: Vec<LadderItem>,
}

impl Ladder {
    pub fn fixed_360_720_1080() -> Self {
        Self {
            items: vec![
                LadderItem{ w:640,  h:360,  v_bitrate_k:  700, a_bitrate_k:128, name:"360p".into() },
                LadderItem{ w:1280, h:720,  v_bitrate_k: 2200, a_bitrate_k:128, name:"720p".into() },
                LadderItem{ w:1920, h:1080, v_bitrate_k: 4500, a_bitrate_k:192, name:"1080p".into() },
            ]
        }
    }

    pub fn from_string(spec: &str) -> Option<Self> {
        // Example: "426x240@400k,640x360@800k,1280x720@2500k"
        let mut items = Vec::new();
        for part in spec.split(',') {
            let p = part.trim();
            let re = regex::Regex::new(r"^(\d+)x(\d+)@(\d+)k(?:/(\d+)k)?(?::(\w+))?$").ok()?;
            let caps = re.captures(p)?;
            let w: u32 = caps.get(1)?.as_str().parse().ok()?;
            let h: u32 = caps.get(2)?.as_str().parse().ok()?;
            let vb: u32 = caps.get(3)?.as_str().parse().ok()?;
            let ab: u32 = caps.get(4).map(|m| m.as_str().parse().ok()).flatten().unwrap_or(128);
            let name = caps.get(5).map(|m| m.as_str().to_string()).unwrap_or(format!("{}p", h));
            items.push(LadderItem{ w, h, v_bitrate_k: vb, a_bitrate_k: ab, name });
        }
        if items.is_empty() { None } else { Some(Self{ items }) }
    }
}

pub fn suggest_ladder_from_dims(w: u32, h: u32) -> Ladder {
    // Simple heuristic: target <= source height; taper bitrates
    let mut base = vec![(640,360,700u32,128u32), (1280,720,2200,128), (1920,1080,4500,192)];
    if h <= 480 { base = vec![(640,360,800,128)]; }
    if h >= 1440 {
        base.push((2560,1440,8000,256));
    }
    if h >= 2160 {
        base.push((3840,2160,14000,320));
    }
    base.retain(|&(_, hh, _, _)| hh <= h);
    Ladder { items: base.into_iter().map(|(w,h,v,a)| LadderItem{w,h,v_bitrate_k:v,a_bitrate_k:a,name:format!("{}p",h)}).collect() }
}
