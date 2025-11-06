use crate::strategy::Strategy;
use clap::{Args, Subcommand};
use std::path::PathBuf;

#[derive(Debug, Subcommand)]
pub(crate) enum Commands {
    #[command(
        name = "watch",
        about = r#"Watch DIR recursively and upload trees marked as ready.
        Uses the sentinel file .bowser.ready to mark a tree as ready for upload."#
    )]
    Watch {
        #[command(flatten)]
        strategy: StrategyArgs,
        #[arg(value_name = "DIR")]
        root: PathBuf,
    },
}

#[derive(Args, Debug)]
#[group(required = true, multiple = false)]
pub struct StrategyArgs {
    #[arg(
        long,
        help = "Watch until a .bowser.complete sentinel file appears in DIR."
    )]
    pub sentinel: bool,
    #[arg(
        long,
        help = "Watch until COUNT .bowser.ready sentinel files have appeared."
    )]
    pub count: Option<usize>,
}

impl From<StrategyArgs> for Strategy {
    fn from(value: StrategyArgs) -> Self {
        match value {
            StrategyArgs { count: Some(n), .. } => Self::Count(n),
            _ => Self::Sentinel,
        }
    }
}
