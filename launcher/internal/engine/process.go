package engine

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

func localURL(port int) string { return "http://127.0.0.1:" + strconv.Itoa(port) }
func command(ctx context.Context, dir string, env []string, name string, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Dir = dir
	if env != nil {
		cmd.Env = env
	}
	prepareProcess(cmd)
	return cmd
}
func (m *Manager) run(t *Task, timeout time.Duration, dir string, env []string, name string, args ...string) error {
	ctx, cancel := context.WithTimeout(m.ctx, timeout)
	defer cancel()
	cmd := command(ctx, dir, env, name, args...)
	writer := &lineWriter{fn: func(s string) { m.log(t, s) }}
	cmd.Stdout = writer
	cmd.Stderr = writer
	if e := cmd.Start(); e != nil {
		return e
	}
	e := cmd.Wait()
	writer.Flush()
	if ctx.Err() != nil {
		return errors.New("任务超时；数据未删除，可重试")
	}
	return e
}

type lineWriter struct {
	mu  sync.Mutex
	buf string
	fn  func(string)
}

func (w *lineWriter) Write(b []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.buf += string(b)
	for {
		idx := strings.IndexByte(w.buf, '\n')
		if idx < 0 {
			break
		}
		line := strings.TrimSpace(w.buf[:idx])
		w.buf = w.buf[idx+1:]
		if line != "" {
			w.fn(line)
		}
	}
	if len(w.buf) > 16384 {
		w.fn(w.buf[:16384])
		w.buf = ""
	}
	return len(b), nil
}
func (w *lineWriter) Flush() {
	w.mu.Lock()
	defer w.mu.Unlock()
	if strings.TrimSpace(w.buf) != "" {
		w.fn(strings.TrimSpace(w.buf))
	}
	w.buf = ""
}
func (m *Manager) childEnv(id string) []string {
	blocked := map[string]bool{"PYTHONPATH": true, "PYTHONHOME": true, "VIRTUAL_ENV": true, "DATA_DIR": true, "GEMINI_API_KEY": true, "GEMINI_MODEL": true, "DECISION_API_KEY": true, "DECISION_MODEL": true, "TTS_API_KEY": true, "TTS_MODEL": true}
	values := map[string]string{}
	for _, item := range os.Environ() {
		k, v, ok := strings.Cut(item, "=")
		if ok && !blocked[strings.ToUpper(k)] {
			values[k] = v
		}
	}
	values["DATA_DIR"] = filepath.Join(m.path(id), "data")
	values["ENABLE_DEMO"] = "true"
	values["PYTHONUNBUFFERED"] = "1"
	values["PYTHONDONTWRITEBYTECODE"] = "1"
	values["PLUGIN_COMMUNITY_URL"] = RepositoryURL
	for k, v := range m.configValues(id) {
		values[k] = v
	}
	result := []string{}
	for k, v := range values {
		result = append(result, k+"="+v)
	}
	return result
}
func availablePort(port int) error {
	listener, e := net.Listen("tcp", "127.0.0.1:"+strconv.Itoa(port))
	if e != nil {
		return fmt.Errorf("端口 %d 已被占用；在实例设置换一个端口", port)
	}
	return listener.Close()
}
func waitHealth(port int, done <-chan struct{}, deadline time.Duration) error {
	client := &http.Client{Timeout: 900 * time.Millisecond}
	end := time.Now().Add(deadline)
	for time.Now().Before(end) {
		select {
		case <-done:
			return errors.New("服务提前退出，请查看日志")
		default:
		}
		r, e := client.Get(localURL(port) + "/api/health")
		if e == nil {
			var h struct {
				OK      bool   `json:"ok"`
				Product string `json:"product"`
			}
			_ = json.NewDecoder(r.Body).Decode(&h)
			r.Body.Close()
			if r.StatusCode == 200 && h.OK && h.Product == "余烬酒馆" {
				return nil
			}
		}
		time.Sleep(180 * time.Millisecond)
	}
	return errors.New("服务健康检查超时，未确认启动成功")
}
func (m *Manager) spawn(id string, t *Task, port int, bind string, env []string) (*runtimeProcess, error) {
	python := m.installedPython(id)
	if python == "" {
		return nil, errors.New("实例尚未安装，请点安装并启动")
	}
	cmd := command(context.Background(), filepath.Join(m.path(id), "app"), env, python, "-m", "uvicorn", "server.app:app", "--host", bind, "--port", strconv.Itoa(port), "--workers", "1", "--ws-max-size", "65536")
	writer := &lineWriter{fn: func(s string) { m.log(t, s) }}
	cmd.Stdout = writer
	cmd.Stderr = writer
	if e := cmd.Start(); e != nil {
		return nil, e
	}
	p := &runtimeProcess{PID: cmd.Process.Pid, done: make(chan struct{}), started: time.Now()}
	p.stop = func() error { return stopProcess(cmd) }
	go func() {
		e := cmd.Wait()
		writer.Flush()
		if e != nil {
			m.log(t, "服务退出："+e.Error())
		}
		close(p.done)
		m.mu.Lock()
		if m.processes[id] == p {
			delete(m.processes, id)
			if e != nil && !m.closing {
				m.errors[id] = "服务已退出，请查看日志"
			}
		}
		m.mu.Unlock()
	}()
	return p, nil
}
func (m *Manager) start(id string, t *Task) error {
	m.mu.Lock()
	i := m.instances[id]
	if m.processes[id] != nil {
		m.mu.Unlock()
		return nil
	}
	port := i.Port
	bind := "127.0.0.1"
	if i.LAN {
		bind = "0.0.0.0"
	}
	m.mu.Unlock()
	if e := availablePort(port); e != nil {
		return e
	}
	if t.Kind == "start" {
		m.progress(t, 96, "启动并确认服务健康")
	}
	p, e := m.spawn(id, t, port, bind, m.childEnv(id))
	if e != nil {
		return e
	}
	if e = waitHealth(port, p.done, 45*time.Second); e != nil {
		_ = p.stop()
		return e
	}
	m.mu.Lock()
	if m.closing {
		m.mu.Unlock()
		_ = p.stop()
		return errors.New("启动器已关闭")
	}
	m.processes[id] = p
	delete(m.errors, id)
	m.mu.Unlock()
	m.log(t, "服务已就绪："+localURL(port))
	return nil
}
func (m *Manager) stop(id string) error {
	m.mu.Lock()
	p := m.processes[id]
	m.mu.Unlock()
	if p == nil {
		return nil
	}
	e := p.stop()
	select {
	case <-p.done:
	case <-time.After(15 * time.Second):
		return errors.New("服务未停止，未执行文件替换")
	}
	m.mu.Lock()
	if m.processes[id] == p {
		delete(m.processes, id)
	}
	delete(m.errors, id)
	m.mu.Unlock()
	if e != nil && !strings.Contains(e.Error(), "already finished") {
		return e
	}
	return nil
}
func (m *Manager) probe(id string, t *Task, data string) error {
	listener, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		return e
	}
	port := listener.Addr().(*net.TCPAddr).Port
	listener.Close()
	env := m.childEnv(id)
	for idx, item := range env {
		if strings.HasPrefix(item, "DATA_DIR=") {
			env[idx] = "DATA_DIR=" + data
		}
	}
	p, e := m.spawn(id, t, port, "127.0.0.1", env)
	if e != nil {
		return e
	}
	defer func() {
		_ = p.stop()
		select {
		case <-p.done:
		case <-time.After(5 * time.Second):
		}
	}()
	return waitHealth(port, p.done, 40*time.Second)
}
func (m *Manager) Logs(id string) []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, t := range m.tasks {
		if t.InstanceID == id {
			if p := m.processes[id]; p != nil && t.Kind == "start" {
				return append([]string{}, t.Logs...)
			}
		}
	}
	rows := []string{}
	for _, t := range m.tasks {
		if t.InstanceID == id {
			rows = append(rows, t.Logs...)
		}
	}
	if len(rows) > 160 {
		rows = rows[len(rows)-160:]
	}
	return rows
}
