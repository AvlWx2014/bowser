use serde::{Deserialize, Serialize};
use std::path::Path;
use tracing::instrument;
use tracing::Level;

const DEFAULT_MIME_TYPE: &'static str = "application/octet-stream";
const MAXIMUM_METADATA_FILE_SIZE: u64 = 8 * 1024; // 8 kB

#[derive(Debug, Serialize, Deserialize)]
struct ContentMetadata {
    mime_type: String,
}

/// Resolve the content type for the file at `path`.
///
/// Resolution follows a fallback chain:
/// 1. Sidecar metadata file (`.{filename}.metadata` in the same directory)
/// 2. Content-based detection via magic bytes (`infer`)
/// 3. Extension-based detection (`mime_guess`)
/// 4. Default: `application/octet-stream`
#[instrument(
        "mime.resolve",
        level = Level::INFO,
)]
pub(crate) async fn resolve(path: &Path) -> String {
    if let Some(ct) = from_sidecar(path).await {
        return ct;
    }
    tracing::debug!("Failed to detect MIME type from metadata sidecar.");
    tracing::debug!("Attempting to detect through magic bytes.");
    if let Some(ct) = from_content(path).await {
        return ct;
    }
    tracing::debug!("Failed to detect MIME type from file content.");
    tracing::debug!("Attempting to detect from file extension.");
    if let Some(ct) = from_extension(path) {
        return ct;
    }
    tracing::debug!(extension = ?path.extension(), "Failed to detect MIME type from file extension.");
    tracing::debug!(
        default = DEFAULT_MIME_TYPE,
        "Falling back to default value."
    );
    DEFAULT_MIME_TYPE.to_string()
}

async fn from_sidecar(path: &Path) -> Option<String> {
    let filename = path.file_name()?.to_str()?;
    let sidecar_name = format!(".{filename}.metadata");
    let sidecar_path = path.parent()?.join(sidecar_name);

    let metadata = tokio::fs::metadata(&sidecar_path).await.ok()?;
    if metadata.len() > MAXIMUM_METADATA_FILE_SIZE {
        tracing::warn!(
            action="ignore",
            size = metadata.len(),
            max = MAXIMUM_METADATA_FILE_SIZE,
            "Sidecar file exceeds maximum size. Please inspect this file as something might be going on."
        );
        return None;
    }

    let contents = tokio::fs::read_to_string(&sidecar_path).await.inspect_err(|it|
        tracing::warn!(cause = ?it, "Error reading JSON metadata sidecar for MIME detection.")
    ).ok()?;

    let content_meta: ContentMetadata = serde_json::from_str(&contents).ok()?;
    match content_meta.mime_type.parse::<mime::Mime>() {
        Ok(parsed) => Some(parsed.to_string()),
        Err(_) => {
            tracing::warn!(value = %content_meta.mime_type, "Sidecar contains invalid MIME type; ignoring.");
            None
        }
    }
}

async fn from_content(path: &Path) -> Option<String> {
    let mut file = match tokio::fs::File::open(path).await {
        Ok(f) => f,
        Err(e) => {
            tracing::warn!(error = %e, "Failed to open file for content-based MIME detection.");
            return None;
        }
    };
    // Many magic numbers fall well within the first 32 bytes of a file
    let mut buf = [0u8; 32];
    let n = match tokio::io::AsyncReadExt::read(&mut file, &mut buf).await {
        Ok(n) => n,
        Err(e) => {
            tracing::warn!(error = %e, "Failed to read file for content-based MIME detection.");
            return None;
        }
    };
    infer::get(&buf[..n]).map(|t| t.mime_type().to_string())
}

fn from_extension(path: &Path) -> Option<String> {
    mime_guess::from_path(path).first().map(|m| m.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_resolve_uses_sidecar_first() {
        let dir = TempDir::new().unwrap();
        // File whose extension would normally resolve to image/png — sidecar overrides it.
        let file = dir.path().join("data.png");
        tokio::fs::write(&file, b"not actually a png")
            .await
            .unwrap();
        let sidecar = dir.path().join(".data.png.metadata");
        tokio::fs::write(
            &sidecar,
            r#"{"mime_type":"application/vnd.apache.parquet"}"#,
        )
        .await
        .unwrap();

        assert_eq!(resolve(&file).await, "application/vnd.apache.parquet");
    }

    #[tokio::test]
    async fn test_resolve_falls_back_to_content_detection() {
        let dir = TempDir::new().unwrap();
        // No sidecar, no recognizable extension; PNG magic bytes identify the type.
        let file = dir.path().join("mystery");
        let png_magic: &[u8] = &[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
        tokio::fs::write(&file, png_magic).await.unwrap();

        assert_eq!(resolve(&file).await, "image/png");
    }

    #[tokio::test]
    async fn test_resolve_falls_back_to_extension() {
        let dir = TempDir::new().unwrap();
        // No sidecar; plain-text content has no magic bytes infer recognizes.
        let file = dir.path().join("data.csv");
        tokio::fs::write(&file, b"a,b,c\n1,2,3\n").await.unwrap();

        assert_eq!(resolve(&file).await, "text/csv");
    }

    #[tokio::test]
    async fn test_resolve_defaults_to_octet_stream() {
        let dir = TempDir::new().unwrap();
        // No sidecar, no recognizable extension, no magic bytes.
        let file = dir.path().join("mystery");
        tokio::fs::write(&file, b"hello world").await.unwrap();

        assert_eq!(resolve(&file).await, "application/octet-stream");
    }

    #[tokio::test]
    async fn test_resolve_falls_back_when_sidecar_has_malformed_json() {
        let dir = TempDir::new().unwrap();
        let file = dir.path().join("data.csv");
        tokio::fs::write(&file, b"a,b,c\n1,2,3\n").await.unwrap();
        let sidecar = dir.path().join(".data.csv.metadata");
        tokio::fs::write(&sidecar, b"not valid json").await.unwrap();

        // Malformed sidecar is ignored; falls through to extension detection.
        assert_eq!(resolve(&file).await, "text/csv");
    }

    #[tokio::test]
    async fn test_resolve_falls_back_when_sidecar_is_empty() {
        let dir = TempDir::new().unwrap();
        let file = dir.path().join("data.csv");
        tokio::fs::write(&file, b"a,b,c\n1,2,3\n").await.unwrap();
        let sidecar = dir.path().join(".data.csv.metadata");
        tokio::fs::write(&sidecar, b"").await.unwrap();

        // Empty sidecar is ignored; falls through to extension detection.
        assert_eq!(resolve(&file).await, "text/csv");
    }

    #[tokio::test]
    async fn test_resolve_content_detection_works_on_large_file() {
        let dir = TempDir::new().unwrap();
        // 1 MB file with PNG magic bytes at the front and zero-padding after.
        let file = dir.path().join("large_image");
        let png_magic: &[u8] = &[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
        let mut content = Vec::with_capacity(1024 * 1024);
        content.extend_from_slice(png_magic);
        content.resize(1024 * 1024, 0);
        tokio::fs::write(&file, &content).await.unwrap();

        // Only the first 32 bytes are read; magic bytes are enough to identify the type.
        assert_eq!(resolve(&file).await, "image/png");
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn test_resolve_falls_back_when_file_has_no_read_permissions() {
        use std::os::unix::fs::PermissionsExt;

        let dir = TempDir::new().unwrap();
        // No sidecar, no extension — content detection is the only path that could succeed,
        // but it will fail to open the file.
        let file = dir.path().join("mystery");
        tokio::fs::write(&file, b"hello world").await.unwrap();

        let mut perms = tokio::fs::metadata(&file).await.unwrap().permissions();
        perms.set_mode(0o000);
        tokio::fs::set_permissions(&file, perms).await.unwrap();

        assert_eq!(resolve(&file).await, "application/octet-stream");
    }
}
