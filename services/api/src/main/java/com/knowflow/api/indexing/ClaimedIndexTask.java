package com.knowflow.api.indexing;

public record ClaimedIndexTask(LeaseContext lease, IndexDispatch dispatch) {}
