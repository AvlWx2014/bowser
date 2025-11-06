use crate::appconfig::AppConfig;
use crate::backends::BowserBackend;
use crate::distinct::DistinctStreamExt;
use crate::realtime::realtime_event_stream;
use crate::replay::replay_event_stream;
use crate::sentinel::Sentinel;
use crate::strategy::Strategy;
use crate::Result;
use futures::future::{join_all, ready};
use futures::stream;
use futures::stream::StreamExt;
use ignore::gitignore::{Gitignore, GitignoreBuilder};
use notify::event::CreateKind;
use notify::{Event, EventKind, RecursiveMode, Watcher};
use std::path::PathBuf;
use std::pin::Pin;
use std::sync::Arc;
use tokio::time::Instant;
use tokio_stream::Stream;
use tracing::Level;
use tracing::{instrument, Instrument};

type PinBoxStream<T> = Pin<Box<dyn Stream<Item=T> + Send>>;


#[instrument(
    "watch",
    level = Level::INFO,
    skip_all,
    fields(root = %root.display(), ?strategy)
)]
pub(crate) async fn watch(config: AppConfig, root: PathBuf, strategy: Strategy, backends: Vec<Box<dyn BowserBackend>>) -> Result<()> {
    let mut ignore = GitignoreBuilder::new(root.clone());
    // ignore Bowser sentinel files by default
    ignore.add_line(None, ".bowser.*")?;
    for pattern in config.bowser.ignore.clone() {
        ignore.add_line(None, &pattern)?;
    }

    let ignore = Arc::new(ignore.build()?);
    let backends = Arc::new(backends);
    let config = Arc::new(config);

    tracing::info!(
            root = %root.display(),
            ?strategy,
            backend_count = backends.len(),
            ignore_pattern_count = config.bowser.ignore.len(),
            "Executing"
        );

    let (realtime, mut watcher) = realtime_event_stream(root.clone())?;
    let replay = replay_event_stream(root.clone());

    let upstream = stream::select_all(
        vec![
            Box::pin(realtime) as PinBoxStream<Event>,
            Box::pin(replay) as PinBoxStream<Event>
        ])
        .filter(|event| {
            ready(matches!(event.kind, EventKind::Create(CreateKind::File)))
        })
        .filter_map(|event| {
            ready(
                event.paths
                    .first()
                    .and_then(Sentinel::try_from_path)
            )
        })
        .take_while(|sentinel| ready(!matches!(sentinel, Sentinel::Abort)))
        .distinct();

    let downstream: PinBoxStream<Sentinel> = match strategy {
        Strategy::Sentinel => {
            Box::pin(
                upstream.take_while(|sentinel| {
                    ready(!matches!(sentinel, Sentinel::Complete(..)))
                })
            )
        },
        Strategy::Count(n) => Box::pin(upstream.take(n))
    };

    tracing::info!("Event stream composition complete");

    tracing::debug!(root = %root.display(), "Starting watcher in recursive mode");
    watcher.watch(&root, RecursiveMode::Recursive)?;
    tracing::info!("Filesystem watcher started");

    tracing::info!("Starting event streaming");
    downstream.for_each_concurrent(None, |it| {
        let backends = backends.clone();
        let config = config.clone();
        let ignore = ignore.clone();

        async move {
            handle(it, backends, config, ignore).await
        }
    }).await;

    Ok(())
}

#[instrument(
    name = "event_handler",
    skip_all,
    fields(sentinel = %sentinel, tree = tracing::field::Empty)
)]
async fn handle(
    sentinel: Sentinel,
    backends: Arc<Vec<Box<dyn BowserBackend>>>,
    config: Arc<AppConfig>,
    ignore: Arc<Gitignore>,
) {
    let parent = match sentinel {
        Sentinel::Ready(ref path) => path.parent().unwrap().to_path_buf(),
        _ => panic!("Unexpected Sentinel processed downstream: expected Sentinel::Ready(path)")
    };

    // Record the tree field now that we have it
    tracing::Span::current().record("tree", parent.display().to_string());
    tracing::info!("Handling sentinel");

    let dry_run = config.bowser.dry_run.unwrap_or_default();
    let start = Instant::now();
    let uploads = backends
        .iter()
        .map(|backend| {
            let parent = parent.clone();
            let ignore = ignore.clone();

            async move {
                let span = tracing::info_span!("backend", %backend);

                async {
                    let result = if dry_run {
                        backend.upload_dry_run(&parent, &ignore).await
                    } else {
                        backend.upload(&parent, &ignore).await
                    };
                    if let Err(ref e) = result {
                        tracing::error!(cause = ?e, "Error in backend upload");
                    };
                    result
                }
                    .instrument(span)
                    .await
                    .ok()
            }
        });

    join_all(uploads).await;
    tracing::info!(elapsed = ?start.elapsed(), directory = %parent.display(), backend_count = backends.len(), "Upload complete");
}

/// Tests authored by Claude Sonnet 4.5.
#[cfg(test)]
mod tests {
    use super::*;
    use crate::appconfig::{AppConfig, BowserConfig};
    use async_trait::async_trait;
    use ignore::gitignore::Gitignore;
    use std::fmt::{Display, Formatter};
    use std::sync::Mutex;
    use tempfile::TempDir;
    use tokio::fs::File;
    use tokio::time::{sleep, Duration};

    /// Mock backend that tracks upload calls for testing
    #[derive(Clone)]
    struct MockBackend {
        root: PathBuf,
        uploaded: Arc<Mutex<Vec<PathBuf>>>,
        dry_run_uploaded: Arc<Mutex<Vec<PathBuf>>>,
    }

    impl MockBackend {
        fn new(root: PathBuf) -> Self {
            Self {
                root,
                uploaded: Arc::new(Mutex::new(Vec::new())),
                dry_run_uploaded: Arc::new(Mutex::new(Vec::new())),
            }
        }

        fn get_uploaded(&self) -> Vec<PathBuf> {
            self.uploaded.lock().unwrap().clone()
        }

        fn get_dry_run_uploaded(&self) -> Vec<PathBuf> {
            self.dry_run_uploaded.lock().unwrap().clone()
        }
    }

    impl Display for MockBackend {
        fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
            write!(f, "MockBackend")
        }
    }

    #[async_trait]
    impl BowserBackend for MockBackend {
        fn watch_root(&self) -> PathBuf {
            self.root.clone()
        }

        async fn upload(&self, tree: &PathBuf, _ignore: &Gitignore) -> crate::backends::Result<()> {
            self.uploaded.lock().unwrap().push(tree.clone());
            Ok(())
        }

        async fn upload_dry_run(&self, tree: &PathBuf, _ignore: &Gitignore) -> crate::backends::Result<()> {
            self.dry_run_uploaded.lock().unwrap().push(tree.clone());
            Ok(())
        }
    }

    fn create_test_config(dry_run: bool) -> AppConfig {
        AppConfig {
            bowser: BowserConfig {
                dry_run: Some(dry_run),
                backends: vec![],
                ignore: vec![],
            },
        }
    }

    async fn create_sentinel_file(dir: &PathBuf, filename: &str) -> std::io::Result<()> {
        let path = dir.join(filename);
        File::create(path).await?;
        Ok(())
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_watch_count_strategy_single_ready() {
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path().to_path_buf();
        let data_dir = root.join("data1");
        tokio::fs::create_dir(&data_dir).await.unwrap();

        let mock_backend = MockBackend::new(root.clone());
        let backends: Vec<Box<dyn BowserBackend>> = vec![Box::new(mock_backend.clone())];

        // Create a .bowser.ready file
        create_sentinel_file(&data_dir, ".bowser.ready").await.unwrap();

        let config = create_test_config(false);
        let strategy = Strategy::Count(1);

        // Give the file system a moment to register the event
        sleep(Duration::from_millis(100)).await;

        // Run watch with count strategy (should process 1 ready sentinel)
        watch(config, root.clone(), strategy, backends).await.unwrap();

        // Verify the backend received the upload call
        let uploaded = mock_backend.get_uploaded();
        assert_eq!(uploaded.len(), 1);
        assert_eq!(uploaded[0], data_dir);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_watch_count_strategy_multiple_ready() {
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path().to_path_buf();

        let data_dir1 = root.join("data1");
        let data_dir2 = root.join("data2");
        tokio::fs::create_dir(&data_dir1).await.unwrap();
        tokio::fs::create_dir(&data_dir2).await.unwrap();

        let mock_backend = MockBackend::new(root.clone());
        let backends: Vec<Box<dyn BowserBackend>> = vec![Box::new(mock_backend.clone())];

        // Create ready sentinels
        create_sentinel_file(&data_dir1, ".bowser.ready").await.unwrap();
        create_sentinel_file(&data_dir2, ".bowser.ready").await.unwrap();

        let config = create_test_config(false);
        let strategy = Strategy::Count(2);

        sleep(Duration::from_millis(100)).await;

        watch(config, root.clone(), strategy, backends).await.unwrap();

        let uploaded = mock_backend.get_uploaded();
        assert_eq!(uploaded.len(), 2);
        assert!(uploaded.contains(&data_dir1));
        assert!(uploaded.contains(&data_dir2));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_watch_sentinel_strategy_stops_on_complete() {
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path().to_path_buf();

        let data_dir = root.join("data1");
        tokio::fs::create_dir(&data_dir).await.unwrap();

        let mock_backend = MockBackend::new(root.clone());
        let backends: Vec<Box<dyn BowserBackend>> = vec![Box::new(mock_backend.clone())];

        // Create ready sentinel then complete sentinel
        create_sentinel_file(&data_dir, ".bowser.ready").await.unwrap();
        create_sentinel_file(&root, ".bowser.complete").await.unwrap();

        let config = create_test_config(false);
        let strategy = Strategy::Sentinel;

        sleep(Duration::from_millis(100)).await;

        watch(config, root.clone(), strategy, backends).await.unwrap();

        // Should have processed the ready, but stopped before any future events
        let uploaded = mock_backend.get_uploaded();
        assert_eq!(uploaded.len(), 1);
        assert_eq!(uploaded[0], data_dir);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_watch_dry_run_mode() {
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path().to_path_buf();
        let data_dir = root.join("data1");
        tokio::fs::create_dir(&data_dir).await.unwrap();

        let mock_backend = MockBackend::new(root.clone());
        let backends: Vec<Box<dyn BowserBackend>> = vec![Box::new(mock_backend.clone())];

        create_sentinel_file(&data_dir, ".bowser.ready").await.unwrap();

        let config = create_test_config(true); // dry_run = true
        let strategy = Strategy::Count(1);

        sleep(Duration::from_millis(100)).await;

        watch(config, root.clone(), strategy, backends).await.unwrap();

        // Should call dry_run, not regular upload
        let uploaded = mock_backend.get_uploaded();
        let dry_run_uploaded = mock_backend.get_dry_run_uploaded();

        assert_eq!(uploaded.len(), 0);
        assert_eq!(dry_run_uploaded.len(), 1);
        assert_eq!(dry_run_uploaded[0], data_dir);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_watch_multiple_backends() {
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path().to_path_buf();
        let data_dir = root.join("data1");
        tokio::fs::create_dir(&data_dir).await.unwrap();

        let mock_backend1 = MockBackend::new(root.clone());
        let mock_backend2 = MockBackend::new(root.clone());
        let backends: Vec<Box<dyn BowserBackend>> = vec![
            Box::new(mock_backend1.clone()),
            Box::new(mock_backend2.clone()),
        ];

        create_sentinel_file(&data_dir, ".bowser.ready").await.unwrap();

        let config = create_test_config(false);
        let strategy = Strategy::Count(1);

        sleep(Duration::from_millis(100)).await;

        watch(config, root.clone(), strategy, backends).await.unwrap();

        // Both backends should receive the upload
        let uploaded1 = mock_backend1.get_uploaded();
        let uploaded2 = mock_backend2.get_uploaded();

        assert_eq!(uploaded1.len(), 1);
        assert_eq!(uploaded2.len(), 1);
        assert_eq!(uploaded1[0], data_dir);
        assert_eq!(uploaded2[0], data_dir);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn test_watch_ignores_non_sentinel_files() {
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path().to_path_buf();
        let data_dir = root.join("data1");
        tokio::fs::create_dir(&data_dir).await.unwrap();

        let mock_backend = MockBackend::new(root.clone());
        let backends: Vec<Box<dyn BowserBackend>> = vec![Box::new(mock_backend.clone())];

        // Create regular files (should be ignored)
        create_sentinel_file(&data_dir, "regular.txt").await.unwrap();
        create_sentinel_file(&data_dir, "data.json").await.unwrap();

        // Create one ready sentinel
        create_sentinel_file(&data_dir, ".bowser.ready").await.unwrap();

        let config = create_test_config(false);
        let strategy = Strategy::Count(1);

        sleep(Duration::from_millis(100)).await;

        watch(config, root.clone(), strategy, backends).await.unwrap();

        // Should only process the sentinel, not regular files
        let uploaded = mock_backend.get_uploaded();
        assert_eq!(uploaded.len(), 1);
    }
}