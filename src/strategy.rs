pub(crate) enum Strategy {
    /// Watch until a .bowser.complete sentinel appears in the watch root.
    Sentinel,
    /// Watch until Count.0 .bowser.ready sentinels have been processed.
    Count(usize),
}