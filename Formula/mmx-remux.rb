class MmxRemux < Formula
  desc "Native Rust remuxer on GStreamer (no FFmpeg)"
  homepage "https://github.com/REPLACE_USER/REPLACE_REPO"
  version "REPLACE_VERSION"

  # Point this to the universal2 tarball uploaded on GitHub Releases
  url "https://github.com/REPLACE_USER/REPLACE_REPO/releases/download/vREPLACE_VERSION/mmx-remux-vREPLACE_VERSION-macos-universal2.tar.gz"
  sha256 "REPLACE_SHA256"

  def install
    bin.install "mmx-remux-v#{version}-macos-universal2" => "mmx-remux"
  end

  test do
    system "#{bin}/mmx-remux", "--help"
  end
end
