use aws_sdk_s3::config::http::HttpResponse;
use aws_sdk_s3::error::SdkError;
use aws_sdk_s3::operation::delete_object::DeleteObjectError;
use aws_sdk_s3::operation::list_objects_v2::ListObjectsV2Error;
use aws_sdk_s3::operation::put_object::PutObjectError;
use derive_more::From;
use std::fmt::{Display, Formatter};
use std::path::PathBuf;

pub(crate) type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, From)]
pub(crate) enum Error {
    // -- For basic, but fallible operations
    #[from(&str, String)]
    BasicStringOperationFailed,

    // -- S3
    S3ByteStreamCreationFailed { from: PathBuf },
    #[from(SdkError<DeleteObjectError, HttpResponse>)]
    S3DeleteObjectFailed,
    #[from(SdkError<ListObjectsV2Error, HttpResponse>)]
    S3ListObjectsFailed,
    #[from(SdkError<PutObjectError, HttpResponse>)]
    S3PutObjectFailed,
    MissingChecksum { key: String },
    ChecksumMismatch,

    // -- WalkDir
    #[from(walkdir::Error)]
    WalkDirFailed,

    // -- std::io
    #[from(std::io::Error)]
    Io,
}

impl Display for Error {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for Error {}
