package engine

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type ModuleRequest struct {
	Operation    string `json:"operation"`
	Archive      string `json:"archive,omitempty"`
	SHA256       string `json:"sha256,omitempty"`
	OldHash      string `json:"old_hash,omitempty"`
	CheckpointID string `json:"checkpoint_id,omitempty"`
	Trust        bool   `json:"trust_backend,omitempty"`
	Grant        bool   `json:"grant_capabilities,omitempty"`
}

func (m *Manager) moduleTool(ctx context.Context, id string, request map[string]any) (json.RawMessage, error) {
	helper := filepath.Join(m.config.BundledSource, "scripts", "plugin_versions.py")
	info, e := os.Lstat(helper)
	if e != nil || !info.Mode().IsRegular() {
		return nil, errors.New("完整桌面缺少模块版本保护工具；保留数据并使用兼容新桌面")
	}
	python := m.installedPython(id)
	if python == "" {
		return nil, errors.New("模块管理需要已安装本体及原独立运行环境")
	}
	request["data_dir"] = filepath.Join(m.path(id), "data")
	m.mu.Lock()
	if instance := m.instances[id]; instance != nil {
		request["host_version"] = instance.Version
	}
	m.mu.Unlock()
	body, e := json.Marshal(request)
	if e != nil || len(body) > 48<<10 {
		return nil, errors.New("模块请求无效")
	}
	cmd := command(ctx, m.config.BundledSource, m.creatorEnv(id), python, helper)
	cmd.Stdin = strings.NewReader(string(body))
	buffer := &creatorBuffer{}
	cmd.Stdout = buffer
	cmd.Stderr = io.Discard
	cmd.Cancel = func() error { return stopProcess(cmd) }
	cmd.WaitDelay = 3 * time.Second
	if e = cmd.Run(); e != nil {
		return nil, errors.New("模块工具未完成；原版及恢复资料保留，请检查任务")
	}
	var result map[string]any
	if json.Unmarshal(buffer.data, &result) != nil {
		return nil, errors.New("模块响应未确认，请保留恢复资料")
	}
	if _, ok := result["ok"].(bool); !ok {
		return nil, errors.New("模块响应格式无效")
	}
	return append(json.RawMessage(nil), buffer.data...), nil
}
func (m *Manager) RecoverModules(id string) error {
	barrier := filepath.Join(m.path(id), "update-journal.json")
	if info, e := os.Lstat(filepath.Join(m.path(id), "module-upgrades")); os.IsNotExist(e) {
		if raw, e := os.ReadFile(barrier); e == nil {
			var value map[string]any
			_ = json.Unmarshal(raw, &value)
			if value["format"] == "ember.module-barrier/v1" {
				return errors.New("模块恢复记录缺失；保持停止并保留数据，不能忽略兼容保护")
			}
		}
		return nil
	} else if e != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return errors.New("模块恢复目录需要检查，原数据保留")
	}
	if e := safeSnapshotPath(m.config.Root, m.path(id)); e != nil {
		return e
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	raw, e := m.moduleTool(ctx, id, map[string]any{"operation": "recover"})
	if e != nil {
		return e
	}
	var result map[string]any
	_ = json.Unmarshal(raw, &result)
	if result["ok"] != true {
		return errors.New("模块事务恢复尚未完成，原快照保留；不要用旧程序强行启动")
	}
	// Only remove our compatibility barrier; never a host update's journal.
	if raw, e := os.ReadFile(barrier); e == nil {
		var value map[string]any
		_ = json.Unmarshal(raw, &value)
		if value["format"] == "ember.module-barrier/v1" {
			return os.Remove(barrier)
		}
	}
	return nil
}
func (m *Manager) ModuleVersions(id string, request ModuleRequest) (Task, error) {
	if !map[string]bool{"preview": true, "history": true, "upgrade": true, "rollback": true}[request.Operation] {
		return Task{}, errors.New("模块操作不受支持")
	}
	mutation := request.Operation == "upgrade" || request.Operation == "rollback"
	if request.Operation == "preview" || request.Operation == "upgrade" {
		if !filepath.IsAbs(request.Archive) || !regexpSHA(request.SHA256) {
			return Task{}, errors.New("需要原生选择的 ZIP 与完整 SHA256")
		}
	}
	if request.Operation == "upgrade" && !regexpSHA(request.OldHash) || request.Operation == "rollback" && !validID(request.CheckpointID) {
		return Task{}, errors.New("请刷新模块版本与快照")
	}
	m.mu.Lock()
	instance := m.instances[id]
	stopped := m.processes[id] == nil
	m.mu.Unlock()
	if instance == nil {
		return Task{}, errors.New("实例不存在")
	}
	if mutation && !stopped {
		return Task{}, errors.New("停止酒馆并等待任务结束后再变更模块")
	}
	kind := "plugin-inspect"
	if mutation {
		kind = "plugin-" + request.Operation
	}
	return m.task(id, kind, func(t *Task) error {
		if e := safeSnapshotPath(m.config.Root, m.path(id)); e != nil {
			return e
		}
		if mutation {
			m.mu.Lock()
			running := m.processes[id] != nil
			m.mu.Unlock()
			if running {
				return errors.New("模块变更需要保持停止")
			}
		}
		body := map[string]any{"operation": request.Operation, "archive": request.Archive, "sha256": request.SHA256, "old_hash": request.OldHash, "checkpoint_id": request.CheckpointID, "transaction_id": t.ID, "trust_backend": request.Trust, "grant_capabilities": request.Grant}
		if mutation {
			m.progress(t, 10, "保存当前完整备份，较新进度与权限保留")
			destination := filepath.Join(m.path(id), "backups", "before-"+t.ID+".zip")
			if e := os.MkdirAll(filepath.Dir(destination), 0700); e != nil {
				return e
			}
			if e := m.run(t, 8*time.Minute, filepath.Join(m.path(id), "app"), m.creatorEnv(id), m.installedPython(id), "scripts/backup.py", "--bundle", "--output", destination); e != nil {
				return e
			}
			if !backupMetadata(destination) {
				return errors.New("完整备份未确认，不变更模块")
			}
		}
		m.progress(t, 40, "审阅版本锁与迁移副本，未确认完成前保持停止")
		ctx, cancel := context.WithTimeout(m.taskContext(t), 3*time.Minute)
		defer cancel()
		raw, e := m.moduleTool(ctx, id, body)
		if e == nil {
			m.mu.Lock()
			t.creatorResult = raw
			m.mu.Unlock()
			var result map[string]any
			_ = json.Unmarshal(raw, &result)
			if result["ok"] != true {
				e = errors.New("模块操作未通过，详情在模块版本管理；原恢复资料保留")
			}
		}
		if mutation {
			if recovery := m.RecoverModules(id); recovery != nil {
				return recovery
			}
		}
		if e != nil {
			return e
		}
		m.progress(t, 100, "模块操作完成；变更后保持停止等待房主复核")
		return nil
	})
}
func regexpSHA(value string) bool {
	if len(value) != 64 {
		return false
	}
	for _, c := range value {
		if !strings.ContainsRune("0123456789abcdef", c) {
			return false
		}
	}
	return true
}
