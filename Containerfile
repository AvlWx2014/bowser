FROM quay.io/automotive-toolchain/rust:1.94.0 as builder
WORKDIR /app
COPY . .
RUN cargo build --release

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
COPY --from=builder /app/target/release/bowser /usr/local/bin/bowser
ENTRYPOINT ["bowser"]