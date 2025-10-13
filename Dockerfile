FROM rust:1-bookworm
WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
RUN cargo build -p mmx-cli -F mmx-core/gst --release
ENTRYPOINT ["target/release/mmx"]
