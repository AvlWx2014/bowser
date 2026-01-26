mod appconfig;
mod backends;
mod checksum;
mod cli;
mod commands;
mod distinct;
mod error;
mod realtime;
mod replay;
mod sentinel;
mod strategy;

pub(crate) use self::error::Result;
use crate::appconfig::{AppConfig, BackendConfig, ConfigOverrides};
use crate::backends::aws::AwsS3Backend;
use crate::backends::BowserBackend;
use crate::cli::Commands;
use clap::Parser;
use commands::watch::watch;
use std::process;
use tracing_subscriber::fmt::format::FmtSpan;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

#[derive(Parser)]
#[command(
    version = "2.0.0",
    about = "Bowser the Warehouser.",
    long_about = "Warehouses your data so you don't have to."
)]
struct Cli {
    #[arg(long, global = true)]
    dry_run: Option<bool>,
    #[command(subcommand)]
    command: Commands,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::fmt::layer()
                .with_target(false)
                .with_span_events(FmtSpan::CLOSE)
                .json(),
        )
        .with(
            tracing_subscriber::EnvFilter::try_from_env("BOWSER_LOG")
                .or_else(|_| tracing_subscriber::EnvFilter::try_from_default_env())
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn,bowser=info")),
        )
        .init();

    let cli = Cli::parse();
    let overrides = ConfigOverrides {
        dry_run: cli.dry_run,
    };
    let config: AppConfig = match AppConfig::try_load(None, Some(overrides)) {
        Ok(config) => config,
        Err(err) => {
            tracing::error!(cause = ?err, "Failed to parse application configuration");
            process::exit(1);
        }
    };

    let exit_code = match cli.command {
        Commands::Watch {
            strategy: strat,
            root,
        } => {
            let strategy = strat.into();
            let backends: Vec<Box<dyn BowserBackend>> = config
                .bowser
                .backends
                .iter()
                .map(|it| match it {
                    BackendConfig::AwsS3 { .. } => {
                        let conf = it.try_into().expect("");
                        Box::new(AwsS3Backend::new(conf, root.clone())) as Box<dyn BowserBackend>
                    }
                })
                .collect();

            match watch(config, root, strategy, backends).await {
                Ok(()) => 0,
                Err(e) => {
                    tracing::error!(cause = ?e, "Error executing command");
                    1
                }
            }
        }
    };

    process::exit(exit_code);
}
