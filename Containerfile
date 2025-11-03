FROM quay.io/automotive-toolchain/rust:1.86.0 as builder
COPY . .
RUN cargo build --release

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
COPY --from=builder /app/src/target/release/bowser /usr/local/bin/bowser
ENTRYPOINT ["bowser"]