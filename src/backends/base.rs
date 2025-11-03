use super::Result;
use async_trait::async_trait;
use ignore::gitignore::Gitignore;
use std::path::PathBuf;

#[async_trait]
pub(crate) trait BowserBackend: Send + Sync {
    fn watch_root(&self) -> PathBuf;
    async fn upload(&self, tree: &PathBuf, ignore: &Gitignore) -> Result<()>;
    async fn upload_dry_run(&self, tree: &PathBuf, ignore: &Gitignore) -> Result<()>;
}

