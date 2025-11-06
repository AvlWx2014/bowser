use crate::Result;
use async_stream::stream;
use futures::stream::StreamExt;
use futures::Stream;
use notify::{recommended_watcher, Event, Watcher};
use std::path::PathBuf;
use tokio::sync::mpsc;
use tokio::sync::mpsc::error::SendError;
use tokio_stream::wrappers::ReceiverStream;

/// Stream file creation events from notify.
pub(crate) fn realtime_event_stream(
    _: PathBuf,
) -> Result<(impl Stream<Item = Event>, impl Watcher)> {
    tracing::debug!("Building realtime event stream");
    let (tx, rx) = mpsc::channel::<Event>(1024);

    let watcher = recommended_watcher(move |result| {
        let span = tracing::trace_span!("realtime.event");
        span.in_scope(|| match result {
            Ok(event) => {
                if let Err(SendError(e)) = tx.blocking_send(event) {
                    tracing::warn!(reason = ?e, "Failed to send event down stream");
                }
            }
            Err(e) => tracing::warn!(reason = ?e, "Error in notify::Watcher event processing"),
        })
    })?;

    let wrapped_stream = stream! {
        let span = tracing::debug_span!("realtime");

        let mut rx = ReceiverStream::new(rx);
        while let Some(event) = rx.next().await {
            yield event;
        }

        // This log happens when the stream is exhausted (receiver dropped)
        span.in_scope(|| {
            tracing::debug!("Realtime event stream completed");
        });
    };

    Ok((wrapped_stream, watcher))
}
