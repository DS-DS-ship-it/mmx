// 0BSD — tiny POSIX-safe shell escaper used by CLI constructing commands
pub fn escape<S: AsRef<str>>(s: S) -> String {
    let s = s.as_ref();
    if s.is_empty() {
        return "''".to_string();
    }
    // allow safe whitelist as-is
    if s.bytes().all(|b| matches!(b,
        b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' |
        b'_' | b'-' | b'.' | b'/' | b':' | b'@' | b'%'
    )) {
        return s.to_string();
    }
    let mut out = String::with_capacity(s.len() + 2);
    out.push('\'');
    for ch in s.chars() {
        if ch == '\'' {
            out.push_str("'\"'\"'");
        } else {
            out.push(ch);
        }
    }
    out.push('\'');
    out
}
