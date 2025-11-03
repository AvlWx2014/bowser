/// Code originally authored by Claude Sonnet 4.5 and adapted to use the pin_project! macro
/// by the project maintainers to mimic how TakeWhile, Map, Filter, etc are implemented
/// in the tokio-streams and futures crates.
///
/// Maintainers additionally removed a superfluous PhantomData marker from the DistinctBy struct:
/// since none of the type parameters are unbounded, the PhantomData marker was not needed.

use futures::stream::Stream;
use pin_project_lite::pin_project;
use std::collections::HashSet;
use std::hash::Hash;
use std::pin::Pin;
use std::task::{Context, Poll};

pub trait DistinctStreamExt: Stream {
    /// Filter out duplicate items based on their value
    fn distinct(self) -> Distinct<Self>
    where
        Self: Sized,
        Self::Item: Hash + Eq + Clone,
    {
        Distinct {
            stream: self,
            seen: HashSet::new(),
        }
    }

    /// Filter out duplicate items based on a key selector function
    fn distinct_by<K, F>(self, selector: F) -> DistinctBy<Self, F, K>
    where
        Self: Sized,
        F: FnMut(&Self::Item) -> K,
        K: Hash + Eq,
    {
        DistinctBy {
            stream: self,
            selector,
            seen: HashSet::new(),
        }
    }
}

impl<T: ?Sized> DistinctStreamExt for T where T: Stream {}

pin_project! {
    pub struct Distinct<S: Stream> {
        #[pin]
        stream: S,
        seen: HashSet<S::Item>,
    }
}


impl<S> Stream for Distinct<S>
where
    S: Stream,
    S::Item: Hash + Eq + Clone,
{
    type Item = S::Item;

    fn poll_next(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        loop {
            match self.as_mut().project().stream.poll_next(cx) {
                Poll::Pending => return Poll::Pending,
                Poll::Ready(None) => return Poll::Ready(None),
                Poll::Ready(Some(item)) => {
                    if self.as_mut().project().seen.insert(item.clone()) {
                        return Poll::Ready(Some(item));
                    }
                },
            }
        }
    }
}

pin_project! {
    pub struct DistinctBy<S: Stream, F, K> {
        #[pin]
        stream: S,
        selector: F,
        seen: HashSet<K>,
    }
}


impl<S, F, K> Stream for DistinctBy<S, F, K>
where
    S: Stream,
    F: FnMut(&S::Item) -> K,
    K: Hash + Eq,
{
    type Item = S::Item;

    fn poll_next(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        loop {
            match self.as_mut().project().stream.poll_next(cx) {
                Poll::Pending => return Poll::Pending,
                Poll::Ready(None) => return Poll::Ready(None),
                Poll::Ready(Some(item)) => {
                    let key = (self.as_mut().project().selector)(&item);
                    if self.as_mut().project().seen.insert(key) {
                        return Poll::Ready(Some(item));
                    }
                }
            }
        }
    }
}