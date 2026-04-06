package usecase

type schedulerHooks struct {
	beforeNodeExecuteFn func(runID string, nodeID string)
}

func (h schedulerHooks) beforeNodeExecute(runID string, nodeID string) {
	if h.beforeNodeExecuteFn != nil {
		h.beforeNodeExecuteFn(runID, nodeID)
	}
}
