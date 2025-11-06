use super::error::{Error, Result};
use crate::appconfig::{BackendConfig, Bucket};
use crate::backends::aws::Error::{ChecksumMismatch, MissingChecksum, S3ByteStreamCreationFailed};
use crate::backends::base::BowserBackend;
use crate::backends::Result as BackendResult;
use crate::checksum;
use async_trait::async_trait;
use aws_config::{Region, SdkConfig};
use aws_credential_types::provider::SharedCredentialsProvider;
use aws_credential_types::Credentials;
use aws_sdk_s3 as s3;
use aws_sdk_s3::primitives::ByteStream;
use aws_sdk_s3::types::ChecksumAlgorithm;
use derive_more::From;
use futures::{stream, StreamExt, TryStreamExt};
use ignore::gitignore::Gitignore;
use ignore::Match;
use pathdiff::diff_paths;
use sec::Secret;
use std::collections::{HashMap, HashSet};
use std::fmt::{Debug, Display, Formatter};
use std::path::PathBuf;
use tokio::time::Instant;
use tracing::instrument;
use tracing::Level;
use walkdir::{DirEntry, WalkDir};

type BucketPrefix = String;
type BucketKey = String;

#[derive(Clone, Debug, From)]
pub(crate) struct AwsS3Config {
    region: String,
    access_key_id: Secret<String>,
    secret_access_key: Secret<String>,
    buckets: Vec<Bucket>,
}

impl TryFrom<BackendConfig> for AwsS3Config {
    type Error = Error;

    fn try_from(value: BackendConfig) -> Result<Self> {
        match value {
            BackendConfig::AwsS3 {
                region,
                access_key_id,
                secret_access_key,
                buckets,
            } => Ok(AwsS3Config {
                region,
                access_key_id,
                secret_access_key,
                buckets,
            }),
        }
    }
}

impl TryFrom<&BackendConfig> for AwsS3Config {
    type Error = Error;

    fn try_from(value: &BackendConfig) -> Result<Self> {
        match value {
            BackendConfig::AwsS3 {
                region,
                access_key_id,
                secret_access_key,
                buckets,
            } => Ok(AwsS3Config {
                region: region.clone(),
                access_key_id: access_key_id.clone(),
                secret_access_key: secret_access_key.clone(),
                buckets: buckets.clone(),
            }),
        }
    }
}

impl From<AwsS3Config> for SdkConfig {
    fn from(value: AwsS3Config) -> Self {
        let credentials = Credentials::from_keys(
            value.access_key_id.reveal().to_string(),
            value.secret_access_key.reveal().to_string(),
            None,
        );
        Self::builder()
            .region(Region::new(value.region))
            .credentials_provider(SharedCredentialsProvider::new(credentials))
            .build()
    }
}

#[derive(Clone)]
pub(crate) struct AwsS3Backend {
    config: AwsS3Config,
    client: s3::Client,
    pub(crate) root: PathBuf,
}

impl Display for AwsS3Backend {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "AwsS3Backend({})", self.config.region)
    }
}

#[derive(Debug)]
enum Op {
    Create { key: String, source: PathBuf },
    Update { key: String, source: PathBuf },
    Delete { key: String },
}

fn s3_client(config: AwsS3Config) -> s3::Client {
    s3::Client::new(&config.into())
}

impl AwsS3Backend {
    pub(crate) fn new(config: AwsS3Config, root: PathBuf) -> Self {
        let client = s3_client(config.clone());
        Self {
            config,
            client,
            root,
        }
    }

    /// Index the source file tree.
    ///
    /// Any nodes that match a pattern in `ignore` are omitted from the resulting
    /// index.
    async fn index_source(
        &self,
        tree: &PathBuf,
        ignore: &Gitignore,
    ) -> Result<HashMap<BucketKey, PathBuf>> {
        tracing::debug!(tree = %tree.display(), "Indexing source tree");
        let start = Instant::now();
        let entries: Vec<DirEntry> = WalkDir::new(tree)
            .sort_by_file_name()
            .into_iter()
            .collect::<std::result::Result<Vec<_>, _>>()?;

        let keys = entries
            .into_iter()
            .filter(|it| it.file_type().is_file())
            .filter_map(|it| {
                let as_path = it.into_path();
                match ignore.matched(&as_path, false) {
                    Match::None | Match::Whitelist(_) => Some(as_path),
                    Match::Ignore(_) => None,
                }
            })
            .filter_map(|entry| self.path_to_key(entry.clone()).map(|it| (it, entry)))
            .collect::<HashMap<_, _>>();

        tracing::debug!(size = keys.len(), elapsed = ?start.elapsed(), "Indexing source tree complete");
        Ok(keys)
    }

    /// Index the destination S3 bucket.
    async fn index_destination(
        &self,
        bucket: &Bucket,
        prefix: BucketPrefix,
    ) -> Result<HashSet<BucketKey>> {
        tracing::debug!(bucket=%bucket.name, %prefix, "Indexing destination");
        let start = Instant::now();

        let client = &self.client;
        let destination = bucket.join_prefix(&prefix).map_err(|_| -> Error {
            format!("Failed to join prefix {:?} + {prefix}", bucket.name).into()
        })?;

        let mut objects = client
            .list_objects_v2()
            .bucket(bucket.name.clone())
            .prefix(destination)
            .into_paginator()
            .send();

        let mut keys = HashSet::new();
        while let Some(object) = objects.try_next().await? {
            object
                .contents
                .unwrap_or_default()
                .iter()
                .filter_map(|obj| obj.key())
                .for_each(|it| {
                    let _ = keys.insert(String::from(it));
                })
        }

        tracing::debug!(size = keys.len(), elapsed = ?start.elapsed(), "Indexing destination complete");
        Ok(keys)
    }

    /// Convert `path` to an S3 object key corresponding to the relative path
    /// between `path` and the watch root.
    ///
    /// In other words, given the path to a file under the watch root, it's S3
    /// key representation is that file's path relative to the watch root.
    fn path_to_key(&self, path: PathBuf) -> Option<BucketKey> {
        diff_paths(path, self.watch_root())?
            .into_os_string()
            .into_string()
            .ok()
    }

    /// Resolve a set of Ops to perform in `bucket` given the tree under `source`.
    ///
    /// Any files in `source` that match a pattern in `ignore` are ignored.
    #[instrument(
        "aws.resolve",
        level = Level::DEBUG,
        skip(self, source, bucket, ignore),
    )]
    async fn resolve(
        &self,
        source: &PathBuf,
        bucket: &Bucket,
        ignore: &Gitignore,
    ) -> Result<Vec<Op>> {
        tracing::debug!("Resolving sync operations to perform");
        let start = Instant::now();
        let mut ops = Vec::<_>::new();

        let prefix = self.path_to_key(source.clone()).ok_or::<Error>(
            format!(
                "Could not resolve sync operations to be done: \
                    failed to translate path {source:?} to a valid S3 key"
            )
            .into(),
        )?;

        let source_index: HashMap<BucketKey, PathBuf> = self
            .index_source(source, ignore)
            .await
            .unwrap_or_default()
            .iter()
            .map(|(key, path)| {
                bucket
                    .join_prefix(key)
                    .map(|it| (it, path.clone()))
                    .map_err(|_| -> Error {
                        format!("Failed to join prefix {:?} + {prefix}", bucket.name).into()
                    })
            })
            .collect::<Result<HashMap<_, _>>>()?;

        let source_keys: HashSet<&BucketKey> = source_index.keys().collect::<HashSet<_>>();

        let destination_index: HashSet<BucketKey> = self
            .index_destination(bucket, prefix.clone())
            .await
            .unwrap_or_default();

        let destination_index = destination_index.iter().collect::<HashSet<_>>();

        source_keys.difference(&destination_index).for_each(|&it| {
            let source = source_index.get(it).unwrap();
            let source = self.watch_root().join(source);
            ops.push(Op::Create {
                key: it.clone(),
                source,
            })
        });

        source_keys
            .intersection(&destination_index)
            .for_each(|&it| {
                let source = source_index.get(it).unwrap();
                let source = self.watch_root().join(source);
                ops.push(Op::Update {
                    key: it.clone(),
                    source,
                })
            });

        destination_index
            .difference(&source_keys)
            .for_each(|&it| ops.push(Op::Delete { key: it.clone() }));

        tracing::debug!(elapsed = ?start.elapsed(), "Complete");
        Ok(ops)
    }

    #[instrument(
        "aws.sync",
        level = Level::INFO,
        skip(self, source, ignore),
        fields(bucket = %bucket.name),
    )]
    async fn sync(&self, source: &PathBuf, bucket: &Bucket, ignore: &Gitignore) -> Result<()> {
        let todos = self.resolve(source, bucket, ignore).await?;
        tracing::info!(
            op_count = todos.len(),
            creates = todos
                .iter()
                .filter(|op| matches!(op, Op::Create { .. }))
                .count(),
            updates = todos
                .iter()
                .filter(|op| matches!(op, Op::Update { .. }))
                .count(),
            deletes = todos
                .iter()
                .filter(|op| matches!(op, Op::Delete { .. }))
                .count(),
            "Sync operations resolved"
        );
        stream::iter(todos)
            .map(Ok)
            .try_for_each_concurrent(
                Some(10),
                |it| async move { self.dispatch(it, bucket).await },
            )
            .await
    }

    #[instrument(
        "aws.sync_dry_run",
        level = Level::INFO,
        skip(self, source, ignore),
        fields(bucket = %bucket.name),
    )]
    async fn sync_dry_run(
        &self,
        source: &PathBuf,
        bucket: &Bucket,
        ignore: &Gitignore,
    ) -> Result<()> {
        let todos = self.resolve(source, bucket, ignore).await?;
        tracing::info!(
            op_count = todos.len(),
            creates = todos
                .iter()
                .filter(|op| matches!(op, Op::Create { .. }))
                .count(),
            updates = todos
                .iter()
                .filter(|op| matches!(op, Op::Update { .. }))
                .count(),
            deletes = todos
                .iter()
                .filter(|op| matches!(op, Op::Delete { .. }))
                .count(),
            "Sync operations resolved"
        );
        for todo in todos.iter() {
            match todo {
                Op::Create { key, source } => {
                    tracing::info!(%key, source = %source.display(), "Would Create")
                }
                Op::Update { key, source } => {
                    tracing::info!(%key, source = %source.display(), "Would Update")
                }
                Op::Delete { key } => tracing::info!(?key, "Would Delete"),
            }
        }
        tracing::info!(op_count = todos.len(), "Sync dry run complete");
        Ok(())
    }

    #[instrument(
        "aws.dispatch",
        level = Level::INFO,
        skip(self, bucket),
        fields(?op),
    )]
    async fn dispatch(&self, op: Op, bucket: &Bucket) -> Result<()> {
        match op {
            Op::Create { key, source } => self.create_object(bucket, key, source).await?,
            Op::Update { key, source } => self.update_object(bucket, key, source).await?,
            Op::Delete { key } => self.delete_object(bucket, key).await?,
        }
        Ok(())
    }

    async fn create_object(&self, bucket: &Bucket, key: String, source: PathBuf) -> Result<()> {
        self.put_object(bucket, key, source).await
    }

    async fn update_object(&self, bucket: &Bucket, key: String, source: PathBuf) -> Result<()> {
        self.put_object(bucket, key, source).await
    }

    #[instrument(
        "aws.put_object",
        level = Level::INFO,
        skip(self, bucket),
        fields(%key, source = %source.display()),
    )]
    async fn put_object(&self, bucket: &Bucket, key: String, source: PathBuf) -> Result<()> {
        let client = self.client.clone();
        let checksum = checksum::sha256(&source).await?;
        let body =
            ByteStream::from_path(&source)
                .await
                .map_err(|_| S3ByteStreamCreationFailed {
                    from: source.clone(),
                })?;

        let response = client
            .put_object()
            .bucket(bucket.name.clone())
            .key(&key)
            .body(body)
            .checksum_algorithm(ChecksumAlgorithm::Sha256)
            .send()
            .await?;

        let actual_checksum = response
            .checksum_sha256
            .ok_or(MissingChecksum { key: key.clone() })?;
        tracing::info!(expected = %checksum, "Verifying checksum");
        if actual_checksum != checksum {
            return Err(ChecksumMismatch);
        }
        tracing::info!("Checksum verified");
        tracing::info!(key = %key, "Object uploaded successfully");
        Ok(())
    }

    #[instrument(
        "aws.delete_object",
        level = Level::INFO,
        skip(self, bucket),
        fields(%key),
    )]
    async fn delete_object(&self, bucket: &Bucket, key: String) -> Result<()> {
        let client = self.client.clone();
        client
            .delete_object()
            .bucket(bucket.name.clone())
            .key(key.clone())
            .send()
            .await?;
        tracing::info!(key = %key, "Object deleted successfully");
        Ok::<(), Error>(())
    }
}

#[async_trait]
impl BowserBackend for AwsS3Backend {
    fn watch_root(&self) -> PathBuf {
        self.root.clone()
    }

    async fn upload(&self, tree: &PathBuf, ignore: &Gitignore) -> BackendResult<()> {
        for bucket in &self.config.buckets {
            self.sync(tree, bucket, ignore).await?;
        }
        Ok(())
    }

    async fn upload_dry_run(&self, tree: &PathBuf, ignore: &Gitignore) -> BackendResult<()> {
        for bucket in &self.config.buckets {
            self.sync_dry_run(tree, bucket, ignore).await?;
        }
        Ok(())
    }
}
