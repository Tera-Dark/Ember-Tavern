package engine

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"sort"
	"time"
)

type taskHistory struct {
	Format string `json:"format"`
	Tasks  []Task `json:"tasks"`
}

const historyFormat = "ember.task-history/v1"

func (m *Manager) TaskHistoryError() string { m.mu.Lock(); defer m.mu.Unlock(); return m.historyError }
func (m *Manager) loadTaskHistory() {
	path := filepath.Join(m.config.Root, "task-history.json")
	info, e := os.Lstat(path)
	if os.IsNotExist(e) {
		return
	}
	bad := func() {
		m.historyError = "任务历史无法读取，原 task-history.json 保留。当前任务仍可运行，但本次不会覆盖旧历史。"
	}
	if e != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Size() > 4<<20 {
		bad()
		return
	}
	b, e := os.ReadFile(path)
	if e != nil {
		bad()
		return
	}
	var history taskHistory
	decoder := json.NewDecoder(bytes.NewReader(b))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&history); e != nil || history.Format != historyFormat || len(history.Tasks) > 100 {
		bad()
		return
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		bad()
		return
	}
	next := map[string]*Task{}
	for _, row := range history.Tasks {
		if !validID(row.ID) || row.ResultInstanceID != "" && !validID(row.ResultInstanceID) || !validID(row.InstanceID) || next[row.ID] != nil || len(row.Kind) > 32 || len(row.Stage) > 1024 || len(row.Error) > 2048 || len(row.Phase) > 32 || len(row.ErrorCode) > 48 || len(row.Logs) > 20 || row.Percent < 0 || row.Percent > 100 || row.TargetTag != "" && !validReleaseTag(row.TargetTag) {
			bad()
			return
		}
		if _, e := time.Parse(time.RFC3339Nano, row.StartedAt); e != nil {
			bad()
			return
		}
		for _, line := range row.Logs {
			if len(line) > 512 {
				bad()
				return
			}
		}
		if row.Status != "success" && row.Status != "failed" && row.Status != "cancelled" && row.Status != "running" {
			bad()
			return
		}
		if m.instances[row.InstanceID] == nil {
			continue
		}
		if row.Status == "running" {
			row.Status = "failed"
			row.Phase = "interrupted"
			row.ErrorCode = "interrupted"
			row.Error = "上次任务中断。引擎已先执行版本事务恢复；请确认实例状态后重新开始。"
			row.Stage = "上次任务未完成，需检查恢复结果"
			row.FinishedAt = timestamp()
		}
		row.Cancellable = false
		row.CancelRequested = false
		next[row.ID] = &row
	}
	m.tasks = next
}
func shortBytes(value string, limit int) string {
	if len(value) <= limit {
		return value
	}
	r := []rune(value)
	for len(string(r)) > limit {
		r = r[:len(r)-1]
	}
	return string(r)
}
func (m *Manager) persistTaskHistoryLocked() {
	if m.historyError != "" {
		return
	}
	rows := []Task{}
	for _, t := range m.tasks {
		row := clone(*t)
		if len(row.Logs) > 20 {
			row.Logs = row.Logs[len(row.Logs)-20:]
		}
		for i, line := range row.Logs {
			row.Logs[i] = shortBytes(line, 512)
		}
		row.Error = shortBytes(row.Error, 2048)
		rows = append(rows, row)
	}
	sort.Slice(rows, func(i, j int) bool {
		a, _ := time.Parse(time.RFC3339Nano, rows[i].StartedAt)
		b, _ := time.Parse(time.RFC3339Nano, rows[j].StartedAt)
		return a.After(b)
	})
	if len(rows) > 100 {
		rows = rows[:100]
	}
	if e := atomicJSON(filepath.Join(m.config.Root, "task-history.json"), taskHistory{Format: historyFormat, Tasks: rows}); e != nil {
		m.historyError = "任务历史保存失败；当前任务仍可查看，请检查数据目录权限与空间。"
	}
}
func (m *Manager) RetryTask(taskID string) (Task, error) {
	m.mu.Lock()
	t := m.tasks[taskID]
	if t == nil || t.Status != "failed" && t.Status != "cancelled" {
		m.mu.Unlock()
		return Task{}, errors.New("仅能重新开始失败或已取消的任务")
	}
	row := clone(*t)
	m.mu.Unlock()
	switch row.Kind {
	case "install":
		return m.Install(row.InstanceID, row.StartAfter)
	case "start":
		return m.Start(row.InstanceID)
	case "stop":
		return m.Stop(row.InstanceID)
	case "update":
		return m.Update(row.InstanceID)
	case "switch":
		if validReleaseTag(row.TargetTag) {
			return m.SwitchVersion(row.InstanceID, row.TargetTag)
		}
	}
	return Task{}, errors.New("此任务需要回到原操作页重新审阅，不能直接重试")
}
func retryable(row Task) bool {
	if row.Status != "failed" && row.Status != "cancelled" {
		return false
	}
	switch row.Kind {
	case "install", "start", "stop", "update":
		return true
	case "switch":
		return validReleaseTag(row.TargetTag)
	}
	return false
}
