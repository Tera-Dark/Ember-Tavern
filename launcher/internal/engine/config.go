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
	values := m.diskSettings(id)
	m.settingsMu.RLock()
	defer m.settingsMu.RUnlock()
	for k, v := range m.runtimeSettings[id] {
		values[k] = v
	}
	return values
}
func (m *Manager) diskSettings(id string) map[string]string {
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
	m.settingsMu.RLock()
	result["_desktop_profile_active"] = len(m.runtimeSettings[id]) > 0
	m.settingsMu.RUnlock()
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
	m.settingsMu.RLock()
	bound := len(m.runtimeSettings[id]) > 0
	m.settingsMu.RUnlock()
	if bound {
		return errors.New("连接档案已应用；先解除档案再编辑旧配置，避免把系统加密的凭据写入旧文件")
	}
	values := m.diskSettings(id)
	if e := applySettings(values, changes); e != nil {
		return e
	}
	return atomicJSON(filepath.Join(m.path(id), "settings.json"), values)
}

// Desktop-only ephemeral overlay. Never persisted in settings.json or version
// snapshots: a previous desktop can still use the untouched legacy settings.
func (m *Manager) SetRuntimeSettings(id string, changes map[string]string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.instances[id] == nil {
		return errors.New("实例不存在")
	}
	if m.active[id] != "" || m.processes[id] != nil {
		return errors.New("停止实例并等待任务结束后再应用连接档案")
	}
	values := map[string]string{}
	for k := range changes {
		if !strings.HasPrefix(k, "DECISION_") && !strings.HasPrefix(k, "TTS_") && !strings.HasPrefix(k, "GEMINI_") {
			return errors.New("连接档案仅允许决策、声音和知识顾问配置")
		}
	}
	if e := applySettings(values, changes); e != nil {
		return e
	}
	m.settingsMu.Lock()
	defer m.settingsMu.Unlock()
	if m.runtimeSettings == nil {
		m.runtimeSettings = map[string]map[string]string{}
	}
	m.runtimeSettings[id] = values
	return nil
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
	// Legacy values remain on disk for older desktops; redact both layers even
	// when an overlay replaces the effective provider key.
	for key, value := range m.diskSettings(id) {
		if isSecret(key) && value != "" {
			line = strings.ReplaceAll(line, value, "[已隐藏]")
		}
	}
	for key, value := range m.configValues(id) {
		if isSecret(key) && value != "" {
			line = strings.ReplaceAll(line, value, "[已隐藏]")
		}
	}
	return line
}
