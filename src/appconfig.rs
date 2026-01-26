use crate::Result;
use config::Config;
use sec::Secret;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use xdg::BaseDirectories;

const BOWSER_DRY_RUN: &str = "bowser.dry_run";

pub(crate) fn config_root() -> PathBuf {
    let base = BaseDirectories::new();
    base.config_home
        .expect("Could not find home directory: is $HOME not set?")
}

#[derive(Default)]
pub(crate) struct ConfigOverrides {
    pub dry_run: Option<bool>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub(crate) struct AppConfig {
    pub(crate) bowser: BowserConfig,
}

impl AppConfig {
    fn parser(sources: &[PathBuf], overrides: ConfigOverrides) -> Result<Config> {
        let mut builder = Config::builder();
        for source in sources {
            builder = builder
                .add_source(config::File::with_name(source.to_str().unwrap()).required(false));
        }

        Ok(builder
            .set_override_option(BOWSER_DRY_RUN, overrides.dry_run)?
            .build()?)
    }

    pub fn try_load(
        from: Option<Vec<PathBuf>>,
        overrides: Option<ConfigOverrides>,
    ) -> Result<AppConfig> {
        let sources = from.unwrap_or_else(|| {
            let config_root = config_root();
            vec![
                PathBuf::from("/etc/bowser/config.toml"),
                PathBuf::from(config_root.join("bowser/config.toml").to_str().unwrap()),
            ]
        });
        let overrides = overrides.unwrap_or_default();
        let parser = AppConfig::parser(&sources, overrides)?;
        Ok(parser.try_deserialize()?)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub(crate) struct BowserConfig {
    /// If `true` then output what work would be done without actually doing it.
    pub(crate) dry_run: Option<bool>,
    pub(crate) backends: Vec<BackendConfig>,
    /// A set of .gitignore-style patterns that should be ignored during upload.
    /// By default, all Bowser sentinel files are ignored (.bowser.*).
    pub(crate) ignore: Option<Vec<String>>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind")]
pub(crate) enum BackendConfig {
    #[serde(rename = "AWS-S3")]
    AwsS3 {
        region: String,
        access_key_id: Secret<String>,
        secret_access_key: Secret<String>,
        buckets: Vec<Bucket>,
    },
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
    pub(crate) prefix: Option<String>,
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
        let result = as_path
            .strip_prefix("/")
            .map(String::from)
            .unwrap_or(as_path);
        Ok(result)
    }
}
