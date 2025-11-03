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
use ignore::gitignore::GitignoreBuilder;
use notify::event::CreateKind;
use notify::{Event, EventKind, RecursiveMode, Watcher};
use std::path::PathBuf;
use std::pin::Pin;
use std::sync::Arc;
use tokio_stream::Stream;

type PinBoxStream<T> = Pin<Box<dyn Stream<Item=T> + Send>>;


pub(crate) async fn watch(config: AppConfig, root: PathBuf, strategy: Strategy, backends: Vec<Box<dyn BowserBackend>>) -> Result<()> {
    println!("Watching {root:?} (config: {config:?})");
    let mut ignore = GitignoreBuilder::new(root.clone());
    // ignore Bowser sentinel files by default
    ignore.add_line(None, ".bowser.*")?;
    for pattern in config.bowser.ignore.clone() {
        ignore.add_line(None, &pattern)?;
    }

    let ignore = Arc::new(ignore.build()?);
    let backends = Arc::new(backends);
    let config = Arc::new(config);

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

    watcher.watch(&root, RecursiveMode::Recursive)?;

    downstream.for_each_concurrent(None, |it| {
        println!("Handling event: {it:?}");

        let backends = backends.clone();
        let config = config.clone();
        let ignore = ignore.clone();

        async move {
            let parent = match it {
                Sentinel::Ready(path) => {
                    path.parent().unwrap().to_path_buf()
                }
                // TODO
                _ => panic!("Unexpected Sentinel processed downstream: expected Sentinel::Ready(path)")
            };

            let uploads = backends
                .iter()
                .map(|backend| {
                    let parent = parent.clone();
                    let config = config.clone();
                    let ignore = ignore.clone();
                    let dry_run = config.bowser.dry_run.unwrap_or_default();

                    async move {
                        let fut = if dry_run { 
                            backend.upload_dry_run(&parent, &ignore)
                        } else { 
                            backend.upload(&parent, &ignore)
                        };
                        let _ = fut.await;
                    }
                });

            join_all(uploads).await;
        }
    }).await;

    Ok(())
}