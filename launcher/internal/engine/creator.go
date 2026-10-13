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

type CreatorRequest struct {
	Operation      string         `json:"operation"`
	Directory      string         `json:"directory"`
	Output         string         `json:"output,omitempty"`
	Kind           string         `json:"kind,omitempty"`
	Identity       string         `json:"identity,omitempty"`
	Name           string         `json:"name,omitempty"`
	Revision       string         `json:"revision,omitempty"`
	RefreshPlugins bool           `json:"refresh_plugins,omitempty"`
	Metadata       map[string]any `json:"metadata,omitempty"`
}
type creatorBuffer struct{ data []byte }

func (b *creatorBuffer) Write(p []byte) (int, error) {
	if len(b.data)+len(p) > 64<<10 {
		return 0, errors.New("creator response exceeds limit")
	}
	b.data = append(b.data, p...)
	return len(p), nil
}

func (m *Manager) creatorEnv(id string) []string {
	result := []string{}
	for _, value := range m.childEnv(id) {
		key, _, _ := strings.Cut(value, "=")
		if strings.HasPrefix(strings.ToUpper(key), "DECISION_") || strings.HasPrefix(strings.ToUpper(key), "GEMINI_") || strings.HasPrefix(strings.ToUpper(key), "TTS_") {
			continue
		}
		result = append(result, value)
	}
	// Empty values also prevent dotenv from importing provider secrets into a tool.
	return append(result, "GEMINI_API_KEY=", "GEMINI_MODEL=", "DECISION_API_KEY=", "DECISION_MODEL=", "DECISION_BASE_URL=", "TTS_API_KEY=", "TTS_MODEL=", "TTS_BASE_URL=")
}
func (m *Manager) Creator(id string, request CreatorRequest) (Task, error) {
	allowed := map[string]bool{"inspect": true, "create": true, "metadata": true, "validate": true, "lock": true, "package": true, "publication": true}
	if !allowed[request.Operation] || !filepath.IsAbs(request.Directory) || len(request.Directory) > 4096 || request.Operation == "package" && (!filepath.IsAbs(request.Output) || len(request.Output) > 4096) {
		return Task{}, errors.New("创作操作或本机目录无效")
	}
	raw, e := json.Marshal(request)
	if e != nil || len(raw) > 48<<10 {
		return Task{}, errors.New("创作请求超过限制")
	}
	helper := filepath.Join(m.config.BundledSource, "scripts", "desktop_creator.py")
	if info, e := os.Lstat(helper); e != nil || !info.Mode().IsRegular() {
		return Task{}, errors.New("此桌面缺少当前创作工具，请使用完整兼容桌面包")
	}
	return m.task(id, "creator", func(t *Task) error {
		python := m.installedPython(id)
		if python == "" {
			return errors.New("先安装一间酒馆，为本机创作提供独立 Python 环境")
		}
		m.progress(t, 25, "本机创作检查，不执行作品代码或发送模型请求")
		ctx, cancel := context.WithTimeout(m.taskContext(t), 45*time.Second)
		defer cancel()
		cmd := command(ctx, m.config.BundledSource, m.creatorEnv(id), python, helper)
		cmd.Stdin = strings.NewReader(string(raw))
		output := &creatorBuffer{}
		cmd.Stdout = output
		cmd.Stderr = io.Discard
		cmd.Cancel = func() error { return stopProcess(cmd) }
		cmd.WaitDelay = 3 * time.Second
		if e := cmd.Run(); e != nil {
			return errors.New("本机创作工具未完成；源作品保留，请检查环境、权限或超时")
		}
		var result map[string]any
		if json.Unmarshal(output.data, &result) != nil {
			return errors.New("本机创作响应无效；原作品保留")
		}
		if _, ok := result["ok"].(bool); !ok {
			return errors.New("本机创作响应格式不受支持")
		}
		m.mu.Lock()
		t.creatorResult = append(json.RawMessage(nil), output.data...)
		m.mu.Unlock()
		if result["ok"] != true {
			return errors.New("作品需要修正；详情在作者工作区，不记录私人正文")
		}
		m.progress(t, 100, "本机创作操作完成，查看作者工作区结果")
		return nil
	})
}
func (m *Manager) CreatorResult(taskID string) (map[string]any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	t := m.tasks[taskID]
	if t == nil || t.Kind != "creator" && t.Kind != "plugin-inspect" && t.Kind != "plugin-upgrade" && t.Kind != "plugin-rollback" {
		return nil, errors.New("创作任务不存在")
	}
	if t.Status == "running" {
		return map[string]any{"done": false}, nil
	}
	if len(t.creatorResult) == 0 {
		return map[string]any{"done": true, "error": "检查结果不再可用，请回到原操作页面重新检查；原文件与恢复资料保留"}, nil
	}
	return map[string]any{"done": true, "result": json.RawMessage(append([]byte(nil), t.creatorResult...))}, nil
}
