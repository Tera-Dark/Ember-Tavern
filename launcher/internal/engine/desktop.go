package engine

import (
	"errors"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

func lanURLs(port int, enabled bool) []string {
	urls := []string{}
	if !enabled {
		return urls
	}
	addresses, _ := net.InterfaceAddrs()
	seen := map[string]bool{}
	for _, address := range addresses {
		ip, _, e := net.ParseCIDR(address.String())
		if e == nil && ip.To4() != nil && ip.IsPrivate() && !ip.IsLoopback() && !seen[ip.String()] {
			urls = append(urls, "http://"+net.JoinHostPort(ip.String(), strconv.Itoa(port)))
			seen[ip.String()] = true
		}
	}
	return urls
}

// The native UI chooses a local ZIP and asks for approval. No shell or arbitrary URL.
func (m *Manager) InstallPlugin(id, archive, sha string, trust, grant bool) (Task, error) {
	if !filepath.IsAbs(archive) || strings.ToLower(filepath.Ext(archive)) != ".zip" || !regexp.MustCompile(`^[a-fA-F0-9]{64}$`).MatchString(sha) {
		return Task{}, errors.New("需要本机 ZIP 和完整 SHA256")
	}
	stat, e := os.Lstat(archive)
	if e != nil || !stat.Mode().IsRegular() || stat.Size() > 10<<20 {
		return Task{}, errors.New("插件 ZIP 无效或超过 10 MiB")
	}
	m.mu.Lock()
	stopped := m.processes[id] == nil
	m.mu.Unlock()
	if !stopped {
		return Task{}, errors.New("安装插件前请停止实例；已有数据保留")
	}
	return m.task(id, "plugin-install", func(t *Task) error {
		m.mu.Lock()
		running := m.processes[id] != nil
		m.mu.Unlock()
		if running {
			return errors.New("请先停止实例")
		}
		python := m.installedPython(id)
		if python == "" {
			return errors.New("请先安装本体")
		}
		m.progress(t, 20, "校验本地包／哈希／权限，不自动运行插件")
		args := []string{"scripts/plugins.py", "install", archive, "--sha256", sha}
		if trust {
			args = append(args, "--trust-backend")
		}
		if grant {
			args = append(args, "--grant-capabilities")
		}
		return m.run(t, 2*time.Minute, filepath.Join(m.path(id), "app"), m.childEnv(id), python, args...)
	})
}
