use crate::Result;
use std::path::PathBuf;
use futures::future::ready;
use futures::{Stream, StreamExt};
use notify::{recommended_watcher, Event, EventKind, Watcher};
use notify::event::CreateKind;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use crate::distinct::DistinctStreamExt;
use crate::sentinel::Sentinel;

/// Stream file creation events from notify.
pub(crate) fn realtime_event_stream(_: PathBuf) -> Result<(impl Stream<Item=Event>, impl Watcher)> {
    let (tx, rx) = mpsc::channel::<Event>(1024);

    let watcher = recommended_watcher(
        move |result| {
            if let Ok(event) = result {
                // TODO: add tracing on failure to send events
                let _ = tx.blocking_send(event);
            }
        },
    )?;

    Ok((ReceiverStream::new(rx), watcher))
}