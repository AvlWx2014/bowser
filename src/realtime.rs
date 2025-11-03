use crate::Result;
use futures::Stream;
use notify::{recommended_watcher, Event, Watcher};
use std::path::PathBuf;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;

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