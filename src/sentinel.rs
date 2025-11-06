use std::fmt::Display;
use std::path::PathBuf;

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub(crate) enum Sentinel {
    Started,
    Abort,
    Ready(PathBuf),
    Complete(PathBuf),
}

impl Sentinel {
    pub(crate) fn try_from_path(path: &PathBuf) -> Option<Self> {
        let filename = path.file_name()?.to_str()?;
        match filename {
            ".bowser.started" => Some(Sentinel::Started),
            ".bowser.abort" => Some(Sentinel::Abort),
            ".bowser.ready" => Some(Sentinel::Ready(path.clone())),
            ".bowser.complete" => Some(Sentinel::Complete(path.clone())),
            _ => None,
        }
    }

    pub(crate) fn to_str(&self) -> &'static str {
        match self {
            Sentinel::Started => "Started",
            Sentinel::Abort => "Abort",
            Sentinel::Ready(..) => "Ready",
            Sentinel::Complete(..) => "Complete",
        }
    }
}

impl From<PathBuf> for Sentinel {
    fn from(value: PathBuf) -> Self {
        Self::try_from_path(&value).expect("PathBuf not recognized as Bowser sentinel")
    }
}

impl Display for Sentinel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let message = match self {
            Sentinel::Started | Sentinel::Abort => format!("{self:?}"),
            Sentinel::Ready(ref inner) | Sentinel::Complete(ref inner) => {
                format!("{}({})", self.to_str(), inner.display())
            }
        };
        write!(f, "{message}")
    }
}

/// Tests authored by Claude Sonnet 4.5.
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_try_from_path_started() {
        let path = PathBuf::from("/some/path/.bowser.started");
        let sentinel = Sentinel::try_from_path(&path);
        assert_eq!(sentinel, Some(Sentinel::Started));
    }

    #[test]
    fn test_try_from_path_abort() {
        let path = PathBuf::from("/some/path/.bowser.abort");
        let sentinel = Sentinel::try_from_path(&path);
        assert_eq!(sentinel, Some(Sentinel::Abort));
    }

    #[test]
    fn test_try_from_path_ready() {
        let path = PathBuf::from("/some/path/.bowser.ready");
        let sentinel = Sentinel::try_from_path(&path);
        assert_eq!(sentinel, Some(Sentinel::Ready(path.clone())));
    }

    #[test]
    fn test_try_from_path_complete() {
        let path = PathBuf::from("/some/path/.bowser.complete");
        let sentinel = Sentinel::try_from_path(&path);
        assert_eq!(sentinel, Some(Sentinel::Complete(path.clone())));
    }

    #[test]
    fn test_try_from_path_non_sentinel() {
        let path = PathBuf::from("/some/path/regular_file.txt");
        let sentinel = Sentinel::try_from_path(&path);
        assert_eq!(sentinel, None);
    }

    #[test]
    fn test_try_from_path_similar_name() {
        let path = PathBuf::from("/some/path/.bowser.ready.backup");
        let sentinel = Sentinel::try_from_path(&path);
        assert_eq!(sentinel, None);
    }

    #[test]
    fn test_try_from_path_no_filename() {
        let path = PathBuf::from("/");
        let sentinel = Sentinel::try_from_path(&path);
        assert_eq!(sentinel, None);
    }

    #[test]
    fn test_from_path_success() {
        let path = PathBuf::from("/some/path/.bowser.ready");
        let sentinel = Sentinel::from(path.clone());
        assert_eq!(sentinel, Sentinel::Ready(path));
    }

    #[test]
    #[should_panic(expected = "PathBuf not recognized as Bowser sentinel")]
    fn test_from_path_panic_on_non_sentinel() {
        let path = PathBuf::from("/some/path/not_a_sentinel.txt");
        let _ = Sentinel::from(path);
    }

    #[test]
    fn test_sentinel_equality() {
        let path1 = PathBuf::from("/path1/.bowser.ready");
        let path2 = PathBuf::from("/path1/.bowser.ready");
        let path3 = PathBuf::from("/path2/.bowser.ready");

        let sentinel1 = Sentinel::Ready(path1);
        let sentinel2 = Sentinel::Ready(path2);
        let sentinel3 = Sentinel::Ready(path3);

        assert_eq!(sentinel1, sentinel2);
        assert_ne!(sentinel1, sentinel3);
    }

    #[test]
    fn test_sentinel_clone() {
        let path = PathBuf::from("/some/path/.bowser.complete");
        let sentinel1 = Sentinel::Complete(path.clone());
        let sentinel2 = sentinel1.clone();
        assert_eq!(sentinel1, sentinel2);
    }

    #[test]
    fn test_sentinel_hash_uniqueness() {
        use std::collections::HashSet;

        let path = PathBuf::from("/some/path/.bowser.ready");
        let mut set = HashSet::new();

        set.insert(Sentinel::Started);
        set.insert(Sentinel::Abort);
        set.insert(Sentinel::Ready(path.clone()));
        set.insert(Sentinel::Complete(path.clone()));

        assert_eq!(set.len(), 4);

        // Inserting duplicates shouldn't increase size
        set.insert(Sentinel::Started);
        set.insert(Sentinel::Ready(path.clone()));

        assert_eq!(set.len(), 4);
    }
}
