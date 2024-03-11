# Bowser the Warehouser

Bowser is a sidekick application that runs as a sidecar container in your Pods and warehouses
your data.

## Usage

#### bowser

```text
Usage: bowser [OPTIONS] COMMAND [ARGS]...

  Warehouses your things for you, whether you like it or not.

Options:
  --debug  Enable debug logging. Warning: this may mean a lot of log output.
  --help   Show this message and exit.

Commands:
  watch  Watch DIR (recursively) and upload trees marked as ready.
```

#### bowser watch

```text
Usage: bowser watch [OPTIONS] DIR

  Watch DIR (recursively) and upload trees marked as ready.

  Use the sentinel file .bowser.ready to mark a tree as ready for upload.

Options:
  --dry-run            If present, AWS calls are mocked using moto and no real
                       upload is done.
  --strategy STRATEGY  Controls what type of event signals the watch command
                       to stop.  [default: sentinel]
  -n, --count INTEGER  If the 'count' watch strategy is chosen, this specifies
                       how many completion events to wait for before stopping.
                       Must be >= 1.
  --help               Show this message and exit.
```

## Configuration

Bowser attempts to load application configuration from the following sources in ascending order
of precedence:

1. `/etc/bowser.toml` (lowest precedence)
2. `$XDG_CONFIG_HOME/bowser/bowser.toml` or `$HOME/.config/bowser/bowser.toml` (highest precedence)
    * Note: `$HOME/.config/bowser/bowser.toml` is used as a fallback in the event
      `$XDG_CONFIG_HOME` is not defined. If both are defined, the `$XDG_CONFIG_HOME` verion is
      loaded, and the `$HOME` version is not.

If more than one of these configuration files exists, configuration is merged in order of
precedence.

Here is an example configuration file:

```toml
[bowser]
dry_run = true

[[bowser.backends]]
kind = "AWS-S3"
region = "eu-west-1"
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

## Watch Strategy

Bowser supports multiple watch strategies for the `watch` subcommand.

### The "Sentinel" Watch Strategy (default)

Stop once a sentinel file called `.bowser.complete` appears in the watch directory.

This is the default watch strategy. If you would like to enable it explicitly, use `--strategy
sentinel` like:

```shell
bowser watch --strategy sentinel /some/dir
```

### The "Count" Watch Strategy

Stop once the specified number of trees have signaled they are upload _ready_. If the upload
operation for a tree fails it still counts towards the number of upload ready trees.

To enable this strategy pass `--strategy count` with the `-n/--count` option like:

```shell
bowser watch --strategy count -n 5 /some/dir
```

If `-n/--count` is used with `--strategy sentinel` it is ignored.

> Note: `count` must be at least 1.

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
region = "eu-west-1"
access_key_id = "access key"
secret_access_key = "secret squirrel stuff"

[[bowser.backends.buckets]]
name = "test-bucket"
prefix = "some/root/prefix"

[[bowser.backends.buckets]]
name = "staging-bucket"
prefix = ""

[[bowser.backends]]
kind = "AWS-S3"
region = "us-east-1"
access_key_id = "access key"
secret_access_key = "secret squirrel stuff"

[[bowser.backends.buckets]]
name = "staging-bucket"
prefix = ""
```

The `region`, `access_key_id`, and `secret_access_key` fields are all required in order for the
S3 client to authenticate with AWS.

Multiple `AWS-S3` backends must be configured if uploading to multiple regions is required.

For each bucket the bucket `name` field needs to match the name of the bucket in the configured
region.

For each bucket the bucket `prefix` field is added as an additional prefix to the resulting
object key before upload. In other words, you can use `prefix` to specify that content should go
under a certain prefix in the target bucket.

#### Implementation Details

* The key for any object that is uploaded includes any ancestor in the path from the watch
  directory `DIR` specified on the command-line to that object, but not `DIR` itself. For
  example, given a watch tree structure like this:

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

then the resulting key for `test2/subtree/content.yml` will be `test2/subtree/content.yml` 
assuming no `key` is specified in your backend bucket configuration. If your bucket definition 
provides `prefix = "some/root/prefix` then the resulting prefix for `test2/subtree/content.yml` will be 
`some/root/prefix/test2/subtree/content.yml`.

* The AWS S3 backend skips uploading any Bowser sentinel files like `.bowser.ready` or
  `.bowser.complete`.
* The AWS S3 backend skips any files with the suffix `.metadata`. It is assumed that `.metadata`
  files are JSON-encoded files with a flat structure of `key: value` pairs of strings. These are
  then translated in to object tags in S3 and as such are subject to the same limitations.
* The system call `inotify` is leveraged for watching the tree rooted at `DIR` through 
  `inotifywait`, which is part of the package `inotify-tools`. `inotifywait` is run using the 
  options `-rmq` i.e. `--recursive`, `--monitor`, and `--quiet` respectively.

