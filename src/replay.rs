use async_stream::stream;
use futures::Stream;
use notify::event::CreateKind;
use notify::{Event, EventKind};
use std::path::PathBuf;
use tokio::task::spawn_blocking;
use walkdir::WalkDir;

/// Stream synthetic file created events from root.
///
/// root is walked top-down and individual files encountered are emitted as synthetic
/// file creation events as if notify had been listening at the time the files were
/// created.
pub(crate) fn replay_event_stream(root: PathBuf) -> impl Stream<Item = Event> {
    stream! {
        if !root.is_dir() {
            return;
        }
        let events = spawn_blocking(move || {
            WalkDir::new(&root)
                .sort_by_file_name()
                .into_iter()
                .filter_map(|it| it.ok())
                .filter(|it| it.file_type().is_file())
                .map(|it| Event::new(EventKind::Create(CreateKind::File)).add_path(it.into_path()))
                .collect::<Vec<_>>()
        })
        .await
        .unwrap_or_default();

        for event in events {
            yield event
        }
    }
}
