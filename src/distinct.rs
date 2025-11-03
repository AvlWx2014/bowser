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

/// Tests authored by Claude Sonnet 4.5.
#[cfg(test)]
mod tests {
    use super::*;
    use futures::stream::{self, StreamExt};

    #[tokio::test]
    async fn test_distinct_empty_stream() {
        let input: Vec<i32> = vec![];
        let result: Vec<i32> = stream::iter(input)
            .distinct()
            .collect()
            .await;

        assert_eq!(result, Vec::<i32>::new());
    }

    #[tokio::test]
    async fn test_distinct_no_duplicates() {
        let input = vec![1, 2, 3, 4, 5];
        let result: Vec<i32> = stream::iter(input.clone())
            .distinct()
            .collect()
            .await;

        assert_eq!(result, input);
    }

    #[tokio::test]
    async fn test_distinct_with_duplicates() {
        let input = vec![1, 2, 2, 3, 1, 4, 3, 5];
        let result: Vec<i32> = stream::iter(input)
            .distinct()
            .collect()
            .await;

        assert_eq!(result, vec![1, 2, 3, 4, 5]);
    }

    #[tokio::test]
    async fn test_distinct_all_same() {
        let input = vec![1, 1, 1, 1, 1];
        let result: Vec<i32> = stream::iter(input)
            .distinct()
            .collect()
            .await;

        assert_eq!(result, vec![1]);
    }

    #[tokio::test]
    async fn test_distinct_with_strings() {
        let input = vec!["apple", "banana", "apple", "cherry", "banana"];
        let result: Vec<&str> = stream::iter(input)
            .distinct()
            .collect()
            .await;

        assert_eq!(result, vec!["apple", "banana", "cherry"]);
    }

    #[tokio::test]
    async fn test_distinct_preserves_order() {
        let input = vec![3, 1, 4, 1, 5, 9, 2, 6, 5];
        let result: Vec<i32> = stream::iter(input)
            .distinct()
            .collect()
            .await;

        // Should preserve first occurrence order
        assert_eq!(result, vec![3, 1, 4, 5, 9, 2, 6]);
    }

    #[tokio::test]
    async fn test_distinct_by_empty_stream() {
        let input: Vec<(i32, &str)> = vec![];
        let result: Vec<(i32, &str)> = stream::iter(input)
            .distinct_by(|item| item.0)
            .collect()
            .await;

        assert_eq!(result, Vec::<(i32, &str)>::new());
    }

    #[tokio::test]
    async fn test_distinct_by_key_selector() {
        let input = vec![
            (1, "apple"),
            (2, "banana"),
            (1, "apricot"),  // Same key as first
            (3, "cherry"),
            (2, "blueberry"), // Same key as second
        ];

        let result: Vec<(i32, &str)> = stream::iter(input)
            .distinct_by(|item| item.0)
            .collect()
            .await;

        assert_eq!(result, vec![
            (1, "apple"),
            (2, "banana"),
            (3, "cherry"),
        ]);
    }

    #[tokio::test]
    async fn test_distinct_by_complex_key() {
        #[derive(Debug, Clone, PartialEq)]
        struct Person {
            id: u32,
            name: String,
            age: u32,
        }

        let input = vec![
            Person { id: 1, name: "Alice".to_string(), age: 30 },
            Person { id: 2, name: "Bob".to_string(), age: 25 },
            Person { id: 1, name: "Alice Smith".to_string(), age: 31 },  // Same ID
        ];

        let result: Vec<Person> = stream::iter(input.clone())
            .distinct_by(|p| p.id)
            .collect()
            .await;

        assert_eq!(result.len(), 2);
        assert_eq!(result[0].id, 1);
        assert_eq!(result[1].id, 2);
    }

    #[tokio::test]
    async fn test_distinct_by_preserves_first() {
        let input = vec![
            (1, "first"),
            (1, "second"),
            (1, "third"),
        ];

        let result: Vec<(i32, &str)> = stream::iter(input)
            .distinct_by(|item| item.0)
            .collect()
            .await;

        // Should keep the first occurrence
        assert_eq!(result, vec![(1, "first")]);
    }
}