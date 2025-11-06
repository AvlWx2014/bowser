mod appconfig;
mod backends;
mod cli;
mod commands;
mod distinct;
mod error;
mod realtime;
mod replay;
mod sentinel;
mod strategy;
mod checksum;

pub(crate) use self::error::Result;
use crate::appconfig::{AppConfig, BackendConfig};
use crate::backends::aws::AwsS3Backend;
use crate::backends::BowserBackend;
use crate::cli::Commands;
use clap::Parser;
use commands::watch::watch;
use config::Config;
use std::path::PathBuf;
use std::process;
use tokio;
use tracing_subscriber::fmt::format::FmtSpan;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use xdg::BaseDirectories;

#[derive(Parser)]
#[command(
    version="2.0.0",
    about="Bowser the Warehouser.",
    long_about="Warehouses your data so you don't have to."
)]
struct Cli {
    #[arg(long, global=true)]
    dry_run: Option<bool>,
    #[command(subcommand)]
    command: Commands,
}


fn config_root() -> PathBuf {
    let base = BaseDirectories::new();
    base.config_home.expect("Could not find home directory: is $HOME not set?")
}


#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::fmt::layer()
                .with_target(false)
                .with_span_events(FmtSpan::CLOSE)
                .json()
        )
        .with(
            tracing_subscriber::EnvFilter::try_from_env("BOWSER_LOG")
                .or_else(|_| tracing_subscriber::EnvFilter::try_from_default_env())
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn,bowser=info"))
        )
        .init();

    let cli = Cli::parse();
    let config_root = config_root();
    let parser = Config::builder()
        .add_source(config::File::with_name("/etc/bowser/config.toml").required(false))
        .add_source(config::File::with_name(config_root.join("bowser/config.toml").to_str().unwrap()))
        .set_override_option("bowser.dry_run", cli.dry_run)
        .expect("Fatal: failed to override dry_run configuration with --dry-run.")
        .build()
        .expect("Failed to parse app configuration");

    let config: AppConfig = match parser.try_deserialize() {
        Ok(config) => config,
        Err(err) => {
            tracing::error!(cause = ?err, "Failed to parse application configuration");
            process::exit(1);
        }
    };

    let exit_code = match cli.command {
        Commands::Watch { strategy: strat, root } => {
            let strategy = strat.into();
            let backends: Vec<Box<dyn BowserBackend>> = config.bowser.backends
                .iter()
                .map(|it| {
                    match it {
                        BackendConfig::AwsS3 { .. } => {
                            let conf = it.try_into().expect("");
                            Box::new(AwsS3Backend::new(conf, root.clone())) as Box<dyn BowserBackend>
                        },
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
