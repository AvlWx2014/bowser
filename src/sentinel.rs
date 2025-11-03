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
            _ => None
        }
    }
}

impl From<PathBuf> for Sentinel {
    fn from(value: PathBuf) -> Self {
        Self::try_from_path(&value)
            .expect("PathBuf not recognized as Bowser sentinel")
    }
}