fn main() {
    println!("cargo:rustc-link-search=native=/opt/homebrew/lib");
    println!("cargo:rustc-link-search=native=/opt/homebrew/opt/glib/lib");
    println!("cargo:rustc-link-search=native=/opt/homebrew/opt/gettext/lib");
    println!("cargo:rustc-link-search=native=/opt/homebrew/opt/gstreamer/lib");
    println!("cargo:rustc-link-search=native=/opt/homebrew/opt/gst-plugins-base/lib");

    println!("cargo:rustc-link-lib=gstreamer-1.0");
    println!("cargo:rustc-link-lib=gobject-2.0");
    println!("cargo:rustc-link-lib=gio-2.0");
    println!("cargo:rustc-link-lib=glib-2.0");
    println!("cargo:rustc-link-lib=intl");
    println!("cargo:rustc-link-lib=iconv");
}
