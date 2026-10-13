package engine

import (
	"context"
	"errors"
)

func (m *Manager) CancelTask(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	t := m.tasks[id]
	if t == nil || t.Status != "running" {
		return errors.New("任务已结束或不存在")
	}
	if !t.Cancellable || t.committing {
		return errors.New("此阶段不能取消；正在保护版本与数据切换，请等待完成")
	}
	t.CancelRequested = true
	t.Cancellable = false
	t.Phase = "cancelling"
	t.Stage = "正在取消准备并清理临时文件；原服务与数据保留"
	t.cancel()
	return nil
}

// Atomic boundary: cancellation either wins before any original service/data
// is touched, or is refused once the transactional switch has begun.
func (m *Manager) beginCommit(t *Task) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if t.ctx != nil && t.ctx.Err() != nil {
		return t.ctx.Err()
	}
	t.committing = true
	t.Cancellable = false
	t.Phase = "committing"
	return nil
}
func (m *Manager) taskContext(t *Task) context.Context {
	if t.ctx != nil {
		return t.ctx
	}
	return m.ctx
}
