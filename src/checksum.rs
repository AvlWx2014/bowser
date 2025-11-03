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

/// Tests authored by Claude Sonnet 4.5.
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[tokio::test]
    async fn test_sha256_empty_file() {
        let temp_file = NamedTempFile::new().unwrap();
        let path = PathBuf::from(temp_file.path());

        let result = sha256(&path).await.unwrap();

        // SHA256 of empty string
        assert_eq!(result, "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=");
    }

    #[tokio::test]
    async fn test_sha256_known_content() {
        let mut temp_file = NamedTempFile::new().unwrap();
        write!(temp_file, "hello world").unwrap();
        temp_file.flush().unwrap();

        let path = PathBuf::from(temp_file.path());
        let result = sha256(&path).await.unwrap();

        // SHA256 of "hello world"
        assert_eq!(result, "uU0nuZNNPgilLlLX2n2r+sSE7+N6U4DukIj3rOLvzek=");
    }

    #[tokio::test]
    async fn test_sha256_large_file() {
        let mut temp_file = NamedTempFile::new().unwrap();
        // Create a file larger than the buffer size (8192 bytes)
        let content = "a".repeat(10000);
        write!(temp_file, "{}", content).unwrap();
        temp_file.flush().unwrap();

        let path = PathBuf::from(temp_file.path());
        let result = sha256(&path).await.unwrap();

        // Should produce a valid base64-encoded SHA256
        assert!(!result.is_empty());
        assert_eq!(result.len(), 44); // Base64 encoded SHA256 is 44 chars
    }

    #[tokio::test]
    async fn test_sha256_binary_content() {
        let mut temp_file = NamedTempFile::new().unwrap();
        let binary_data: Vec<u8> = vec![0x00, 0x01, 0x02, 0xff, 0xfe, 0xfd];
        temp_file.write_all(&binary_data).unwrap();
        temp_file.flush().unwrap();

        let path = PathBuf::from(temp_file.path());
        let result = sha256(&path).await.unwrap();

        // Should handle binary data correctly
        assert!(!result.is_empty());
        assert_eq!(result.len(), 44);
    }

    #[tokio::test]
    async fn test_sha256_nonexistent_file() {
        let path = PathBuf::from("/this/path/does/not/exist/file.txt");
        let result = sha256(&path).await;

        assert!(result.is_err());
        assert_eq!(result.unwrap_err().kind(), std::io::ErrorKind::NotFound);
    }

    #[tokio::test]
    async fn test_sha256_deterministic() {
        let mut temp_file = NamedTempFile::new().unwrap();
        write!(temp_file, "test content").unwrap();
        temp_file.flush().unwrap();

        let path = PathBuf::from(temp_file.path());

        // Run twice, should get same result
        let result1 = sha256(&path).await.unwrap();
        let result2 = sha256(&path).await.unwrap();

        assert_eq!(result1, result2);
    }

    #[tokio::test]
    async fn test_sha256_different_content_different_hash() {
        let mut temp_file1 = NamedTempFile::new().unwrap();
        let mut temp_file2 = NamedTempFile::new().unwrap();

        write!(temp_file1, "content A").unwrap();
        temp_file1.flush().unwrap();

        write!(temp_file2, "content B").unwrap();
        temp_file2.flush().unwrap();

        let path1 = PathBuf::from(temp_file1.path());
        let path2 = PathBuf::from(temp_file2.path());

        let hash1 = sha256(&path1).await.unwrap();
        let hash2 = sha256(&path2).await.unwrap();

        assert_ne!(hash1, hash2);
    }
}
