use base64::{engine::general_purpose, Engine as _};
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use tokio::fs::File;
use tokio::io::AsyncReadExt;

/// Compute the SHA-256 checksum for input.
pub(crate) async fn sha256(input: &PathBuf) -> std::io::Result<String> {
    let mut file = File::open(input).await?;
    let mut hash_slinging_slasher = Sha256::new();
    let mut buffer = vec![0; 8192];

    while let Ok(n) = file.read(&mut buffer).await {
        if n == 0 { break; }
        hash_slinging_slasher.update(&buffer[..n]);
    }

    let digest = hash_slinging_slasher.finalize();
    Ok(general_purpose::STANDARD.encode(&digest))
}
