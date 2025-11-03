use crate::Result;
use sec::Secret;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;


#[derive(Clone, Debug, Serialize, Deserialize)]
pub(crate) struct AppConfig {
    pub(crate) bowser: BowserConfig
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub(crate) struct BowserConfig {
    /// If `true` then output what work would be done without actually doing it.
    pub(crate) dry_run: Option<bool>,
    pub(crate) backends: Vec<BackendConfig>,
    /// A set of .gitignore-style patterns that should be ignored during upload.
    /// By default, all Bowser sentinel files are ignored (.bowser.*).
    pub(crate) ignore: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag="kind")]
pub(crate) enum BackendConfig {
    #[serde(rename="AWS-S3")]
    AwsS3 {
        region: String,
        access_key_id: Secret<String>,
        secret_access_key: Secret<String>,
        buckets: Vec<Bucket>
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub(crate) struct Bucket {
    /// The target bucket name.
    pub(crate) name: String,
    /// The root prefix objects should be uploaded under.
    ///
    /// The default value is "" (the empty string) which means content will be sync'd
    /// directly to the top-level of the given bucket name.
    ///
    /// If prefix is not empty, then content will be sync'd under the provided prefix.
    pub(crate) prefix: Option<String>
}

impl Bucket {
    /// Join this bucket's prefix field, if present, with the prefix argument.
    ///
    /// This has the effect of creating an "absolute path" or key under this Bucket.
    ///
    /// Joining is done by treating both this bucket's prefix and the prefix argument
    /// as path parts. If the two parts cannot be sensibly joined together like path parts
    /// then this can fail.
    pub(crate) fn join_prefix(&self, prefix: impl Into<String>) -> Result<String> {
        let root = self.prefix.clone().unwrap_or("/".to_string());
        let as_path = PathBuf::from(root)
            .join(prefix.into())
            .into_os_string()
            .into_string()?;
        let result = as_path.strip_prefix("/")
            .map(String::from)
            .unwrap_or(as_path);
        Ok(result)
    }
}