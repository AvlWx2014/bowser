use super::error::{Error, Result};
use crate::appconfig::{BackendConfig, Bucket};
use crate::backends::aws::Error::{ChecksumMismatch, MissingChecksum, S3ByteStreamCreationFailed};
use crate::backends::base::BowserBackend;
use crate::backends::Result as BackendResult;
use async_trait::async_trait;
use aws_config;
use aws_config::{Region, SdkConfig};
use aws_credential_types::provider::SharedCredentialsProvider;
use aws_credential_types::Credentials;
use aws_sdk_s3 as s3;
use aws_sdk_s3::primitives::ByteStream;
use derive_more::From;
use futures::{stream, StreamExt, TryStreamExt};
use pathdiff::diff_paths;
use sec::Secret;
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use aws_sdk_s3::types::ChecksumAlgorithm;
use ignore::gitignore::Gitignore;
use ignore::Match;
use walkdir::{DirEntry, WalkDir};
use crate::checksum;

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

impl Into<SdkConfig> for AwsS3Config {
    fn into(self) -> SdkConfig {
        let credentials = Credentials::from_keys(
            self.access_key_id.reveal().to_string(),
            self.secret_access_key.reveal().to_string(),
            None,
        );
        SdkConfig::builder()
            .region(Region::new(self.region))
            .credentials_provider(SharedCredentialsProvider::new(credentials))
            .build()
    }
}

#[derive(Clone, Debug)]
pub(crate) struct AwsS3Backend {
    config: AwsS3Config,
    client: s3::Client,
    pub(crate) root: PathBuf,
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
    async fn index_source(&self, tree: &PathBuf, ignore: &Gitignore) -> Result<HashMap<BucketKey, PathBuf>> {
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
            .filter_map(|entry| {
                self.path_to_key(entry.clone())
                    .map(|it| (it, entry))
            })
            .collect::<HashMap<_, _>>();

        Ok(keys)
    }

    /// Index the destination S3 bucket.
    async fn index_destination(
        &self,
        bucket: &Bucket,
        prefix: BucketPrefix,
    ) -> Result<HashSet<BucketKey>> {
        println!("Listing {prefix} in {bucket:?}");
        let client = &self.client;
        let destination = bucket.join_prefix(&prefix)
            .map_err(|_| -> Error {
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
                    println!("Object key: {it:?}");
                    let _ = keys.insert(String::from(it));
                })
        }

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
    async fn resolve(&self, source: &PathBuf, bucket: &Bucket, ignore: &Gitignore) -> Result<Vec<Op>> {
        let mut ops = Vec::<_>::new();

        let prefix = self.path_to_key(source.clone())
            .ok_or::<Error>(
                format!(
                    "Could not resolve sync operations to be done: \
                    failed to translate path {source:?} to a valid S3 key"
                ).into()
            )?;

        let source_index: HashMap<BucketKey, PathBuf> = self.index_source(source, ignore)
            .await
            .unwrap_or_default()
            .iter()
            .map(|(key, path)| {
                bucket.join_prefix(key)
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

        source_keys.difference(&destination_index)
            .for_each(|&it| {
                let source = source_index.get(it).unwrap();
                let source = self.watch_root().join(source);
                ops.push(Op::Create { key: it.clone(), source })
            });

        source_keys.intersection(&destination_index)
            .for_each(|&it| {
                let source = source_index.get(it).unwrap();
                let source = self.watch_root().join(source);
                ops.push(
                    Op::Update { key: it.clone(), source }
                )
            });

        destination_index.difference(&source_keys)
            .for_each(|&it| ops.push(Op::Delete { key: it.clone() }));

        Ok(ops)
    }

    async fn sync(&self, source: &PathBuf, bucket: &Bucket, ignore: &Gitignore) -> Result<()> {
        let todos = self.resolve(source, bucket, ignore).await?;
        stream::iter(todos)
            .map(Ok)
            .try_for_each_concurrent(Some(10), |it| async move {
                self.dispatch(it, bucket).await
            })
            .await?;
        Ok(())
    }

    async fn sync_dry_run(&self, source: &PathBuf, bucket: &Bucket, ignore: &Gitignore) -> Result<()> {
        let todos = self.resolve(source, bucket, ignore).await?;

        for todo in todos {
            match todo {
                Op::Create { key, source } => println!("Would Create {key} from {source:?}"),
                Op::Update { key, source } => println!("Would Update {key} with {source:?}"),
                Op::Delete { key } => println!("Would Delete {key}"),
            }
        }
        Ok(())
    }

    async fn dispatch(&self, op: Op, bucket: &Bucket) -> Result<()> {
        println!("Dispatching op {op:?} to {bucket:?}");
        match op {
            Op::Create { key, source } => self.create_object(bucket, key, source).await?,
            Op::Update { key, source } => self.update_object(bucket, key, source).await?,
            Op::Delete { key } => self.delete_object(bucket, key).await?,
        }
        Ok(())
    }

    async fn create_object(&self, bucket: &Bucket, key: String, source: PathBuf) -> Result<()> {
        println!("Creating object {}/{key} from {source:?}", bucket.name);
        self.put_object(bucket, key, source).await
    }

    async fn update_object(&self, bucket: &Bucket, key: String, source: PathBuf) -> Result<()> {
        println!("Updating object {}/{key} with {source:?}", bucket.name);
        self.put_object(bucket, key, source).await
    }

    async fn put_object(&self, bucket: &Bucket, key: String, source: PathBuf) -> Result<()> {
        let client = self.client.clone();
        let checksum = checksum::sha256(&source).await?;
        let body = ByteStream::from_path(&source)
            .await
            .map_err(|_| S3ByteStreamCreationFailed { from: source.clone() })?;

        let response = client.put_object()
            .bucket(bucket.name.clone())
            .key(&key)
            .body(body)
            .checksum_algorithm(ChecksumAlgorithm::Sha256)
            .send()
            .await?;

        let actual_checksum = response.checksum_sha256.ok_or(MissingChecksum { key })?;
        if actual_checksum != checksum {
            return Err(ChecksumMismatch)
        }
        Ok(())
    }

    async fn delete_object(&self, bucket: &Bucket, key: String) -> Result<()> {
        println!("Deleting object {}/{key}", bucket.name);
        let client = self.client.clone();
        client.delete_object()
            .bucket(bucket.name.clone())
            .key(key)
            .send()
            .await?;
        Ok(())
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
