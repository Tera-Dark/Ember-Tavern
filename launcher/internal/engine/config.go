package engine

import (
	"encoding/json"
	"errors"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

var AllowedSettings = map[string]bool{"GEMINI_API_KEY": true, "GEMINI_MODEL": true, "DECISION_API_KEY": true, "DECISION_BASE_URL": true, "DECISION_MODEL": true, "DECISION_JSON_MODE": true, "TTS_API_KEY": true, "TTS_BASE_URL": true, "TTS_MODEL": true, "TTS_VOICE": true, "ENABLE_DEMO": true, "AI_TIMEOUT_SECONDS": true, "SESSION_HOURS": true}

func (m *Manager) configValues(id string) map[string]string {
	values := map[string]string{}
	b, e := os.ReadFile(filepath.Join(m.path(id), "settings.json"))
	if e == nil {
		_ = json.Unmarshal(b, &values)
	}
	return values
}
func (m *Manager) Settings(id string) (map[string]any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.instances[id] == nil {
		return nil, errors.New("实例不存在")
	}
	result := map[string]any{}
	for k, v := range m.configValues(id) {
		if isSecret(k) {
			result[k+"_configured"] = v != ""
		} else {
			result[k] = v
		}
	}
	return result, nil
}
func (m *Manager) SaveSettings(id string, changes map[string]string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.instances[id] == nil {
		return errors.New("实例不存在")
	}
	if m.active[id] != "" || m.processes[id] != nil {
		return errors.New("停止实例后再修改配置")
	}
	values := m.configValues(id)
	if e := applySettings(values, changes); e != nil {
		return e
	}
	return atomicJSON(filepath.Join(m.path(id), "settings.json"), values)
}

// Shared by explicit settings edits and conservative legacy recovery. Error
// messages name no supplied value, so provider credentials cannot be echoed.
func applySettings(values, changes map[string]string) error {
	for k, v := range changes {
		if !AllowedSettings[k] {
			return errors.New("不支持的配置项")
		}
		if len(v) > 2048 || strings.ContainsAny(v, "\n\r\x00") {
			return errors.New("配置值不合法")
		}
		v = strings.TrimSpace(v)
		if strings.HasSuffix(k, "BASE_URL") {
			if v == "" {
				delete(values, k)
				continue
			}
			u, e := url.Parse(v)
			if e != nil || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
				return errors.New("接口地址不合法；密钥不要放在 URL")
			}
			if u.Scheme != "https" && (u.Scheme != "http" || (u.Hostname() != "localhost" && u.Hostname() != "127.0.0.1")) {
				return errors.New("接口需要 HTTPS，本机服务可用 HTTP")
			}
		}
		if k == "TTS_VOICE" && v == "" {
			delete(values, k)
			continue
		}
		values[k] = v
	}
	return nil
}
func isSecret(key string) bool {
	return strings.Contains(key, "KEY") || strings.Contains(key, "TOKEN") || strings.Contains(key, "PASSWORD")
}
func (m *Manager) redact(id, line string) string {
	for key, value := range m.configValues(id) {
		if isSecret(key) && value != "" {
			line = strings.ReplaceAll(line, value, "[已隐藏]")
		}
	}
	return line
}
