use derive_more::From;
use std::fmt::{Display, Formatter};

/// Top-level Result type.
///
/// Results and Errors are hierarchical throughout the application where
/// lower layers propagate errors up to higher layers where they're
/// converted to more generic errors through the combination of derive_more's
/// From and #[from] and the ? operator.
pub(crate) type Result<T> = std::result::Result<T, Error>;


#[derive(Debug, From)]
pub(crate) enum Error {
    #[from(notify::Error)]
    Notify,

    #[from(std::ffi::OsString)]
    Os,

    #[from(ignore::Error)]
    PathMatching,
}

impl Display for Error {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for Error {}
