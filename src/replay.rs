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
///
/// Files are sorted by depth (deeper first) then by filename. This ensures that
/// sentinel files in subdirectories (like data/.bowser.ready) are processed before
/// sentinel files in the root (like .bowser.complete), allowing proper sequencing
/// of watch termination.
pub(crate) fn replay_event_stream(root: PathBuf) -> impl Stream<Item = Event> {
    stream! {
        if !root.is_dir() {
            return;
        }
        // async events resolution authored by Claude Sonnet 4.5
        // to account for a bug found in the original implementation during testing
        let events = spawn_blocking(move || {
            let mut entries: Vec<_> = WalkDir::new(&root)
                .into_iter()
                .filter_map(|it| it.ok())
                .filter(|it| it.file_type().is_file())
                .collect();

            // Sort by depth (descending) then by file name
            // This ensures deeper files are processed first
            entries.sort_by(|a, b| {
                let depth_cmp = b.depth().cmp(&a.depth());
                if depth_cmp == std::cmp::Ordering::Equal {
                    a.file_name().cmp(b.file_name())
                } else {
                    depth_cmp
                }
            });

            entries
                .into_iter()
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
