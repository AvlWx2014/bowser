use crate::backends::aws;
use derive_more::From;
use std::fmt::{Display, Formatter};

pub(crate) type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, From)]
pub(crate) enum Error {
    #[from(aws::Error)]
    AwsError,
}

impl Display for Error {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for Error {}
