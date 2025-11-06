# Bowser the Warehouser

Bowser is a sidekick application that runs as a sidecar to your Kubernetes applications and warehouses your data.

## Usage

#### bowser

```text
Warehouses your data so you don't have to.

Usage: bowser [OPTIONS] <COMMAND>

Commands:
  watch  Watch DIR recursively and upload trees marked as ready.
         Uses the sentinel file .bowser.ready to mark a tree as ready for upload.
  help   Print this message or the help of the given subcommand(s)

Options:
      --dry-run <DRY_RUN>
          [possible values: true, false]

  -h, --help
          Print help (see a summary with '-h')

  -V, --version
          Print version
```

#### bowser watch

```text
Watch DIR recursively and upload trees marked as ready.
Uses the sentinel file .bowser.ready to mark a tree as ready for upload.

Usage: bowser watch [OPTIONS] <--sentinel|--count <COUNT>> <DIR>

Arguments:
  <DIR>  

Options:
      --dry-run <DRY_RUN>  [possible values: true, false]
      --sentinel           Watch until a .bowser.complete sentinel file appears in DIR. 
                           Mutually exclusive with --count.
      --count <COUNT>      Watch until COUNT .bowser.ready sentinel files have appeared.
                           Mutually exclusive with --sentinel.
  -h, --help               Print help
```

## Configuration

Bowser attempts to load application configuration from the following sources in ascending order
of precedence:

1. `/etc/bowser.toml` (lowest precedence)
2. `$XDG_CONFIG_HOME/bowser/bowser.toml` or `$HOME/.config/bowser/bowser.toml` (highest precedence)
    * Note: `$HOME/.config/bowser/bowser.toml` is used as a fallback in the event
      `$XDG_CONFIG_HOME` is not defined. If both are defined, the `$XDG_CONFIG_HOME` path is preferred.

Here is an example configuration file:

```toml
[bowser]
dry_run = true
# .gitignore style patterns to be ignored
ignore = [
    "*.metadata"
]

[[bowser.backends]]
kind = "AWS-S3"
region = "us-east-1"
access_key_id = "access key"
secret_access_key = "secret squirrel stuff"

[[bowser.backends.buckets]]
name = "a literal bucket"
prefix = "some/root/prefix"
```

These select configuration fields in the root `bowser` table can be overridden with the highest
precedence as command line flags:

| Configuration Field | Corresponding Command-line Option | Subcommand Scope |
|---------------------|-----------------------------------|------------------|
| `dry_run`           | `--dry-run`                       | `watch`          |

## Ignoring Files

Bowser's configuration schema provides `bowser.ignore` to specify patterns which represent files 
that should be ignored during upload.

By default, all Bowser sentinel files like `.bowser.ready`, `.bowser.complete`, etc. are ignored. 
Additional ignores can be configured like so:

```toml
[bowser]
ignore = [
    "*.tmp"
]
```

`[bowser.ignore]` supports gitignore-style patterns courtesy of the [`ignore`](https://docs.rs/ignore/latest/ignore/)
crate.

## Watch Strategy

Bowser supports multiple watch strategies for the `watch` subcommand.

### The "Sentinel" Watch Strategy (default)

Stop once a sentinel file called `.bowser.complete` appears in the watch directory.

This is the default watch strategy. If you would like to enable it explicitly, use the `--sentinel` 
flag like:

```shell
bowser watch --sentinel /some/dir
```

### The "Count" Watch Strategy

Stop once the specified number of trees have signaled they are upload _ready_. If the upload
operation for a tree fails it still counts towards the number of upload ready trees.

To enable this strategy pass `--count N` like:

```shell
bowser watch --count 5 /some/dir
```

> Note: `--count` must have a value of at least 1.

## Bowser Backends

Bowser uses the concept of a "Bowser Backend" to handle the actual upload logic. Each backend
has its own configuration schema, and more than one backend can be configured to upload the same
data.

This is useful if, for example, you need to support uploading to short-term and long-term
storage at the same time, or if you need to support parallel uploads while you're transitioning
from one storage backend to another.

Bowser currently supports the following backends:

| Storage Backend | Configuration Kind | 
|-----------------|--------------------|
| AWS S3          | "AWS-S3"           |

### The AWS S3 Backend

The AWS S3 backend supports the configuration of multiple buckets for each set of access
credentials.

For example, if you would like to upload to a staging and test bucket at the same time using the
same service account credentials, you can configure your AWS S3 backend to do so. The same
underlying client will be used to upload to each bucket.

Here is an example backend configuration:

```toml
[[bowser.backends]]
kind = "AWS-S3"
region = "us-east-1"
access_key_id = "access key"
secret_access_key = "secret squirrel stuff"

[[bowser.backends.buckets]]
name = "test-bucket"
prefix = "some/root/prefix"

[[bowser.backends.buckets]]
name = "staging-bucket"

[[bowser.backends]]
kind = "AWS-S3"
region = "eu-west-1"
access_key_id = "access key 2"
secret_access_key = "secret squirrel stuff 2"

[[bowser.backends.buckets]]
name = "staging-bucket"
```

The `region`, `access_key_id`, and `secret_access_key` fields are all required in order for the
S3 client to authenticate with AWS.

Multiple `AWS-S3` backends must be configured if uploading to multiple regions is required.

For each bucket the bucket `name` field needs to match the name of the bucket in the configured
region.

For each bucket the bucket `prefix` field is added as an additional prefix prepended to each object key
before upload. In other words, you can use `prefix` to specify that content should go under a certain 
prefix in the target bucket.

#### Implementation Details

* The key for any object that is uploaded includes any ancestor in the path from the watch directory `DIR` 
  specified on the command-line to that object, but not `DIR` itself. In other words: it is the path to the 
  object relative to `DIR`. For example, given a watch tree structure like this:

```text
/tmp/transient-fortitude/
├── test1
│   └── content.txt
├── test2
│   ├── subdir
│   └── subtree
│       └── content.yml
├── test3
│   ├── content.metadata
│   └── content.txt
├── test4
│   ├── subdir
│   └── subtree
│       └── content.yml
└── test5
    ├── content.metadata
    └── content.txt
```

the resulting key for `/tmp/transient-fortitude/test2/subtree/content.yml` would be `test2/subtree/content.yml` 
assuming no additional `prefix` is specified in your backend bucket configuration. If your bucket definition 
provides `prefix = "some/root/prefix"` then the resulting prefix for `/tmp/transient-fortitude/test2/subtree/content.yml` 
would be `some/root/prefix/test2/subtree/content.yml`.
