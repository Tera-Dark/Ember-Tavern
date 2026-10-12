package engine

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

const LauncherVersion = "0.2.0-beta.4"
const Repository = "Tera-Dark/Ember-Tavern"
const RepositoryURL = "https://github.com/" + Repository
const PythonVersion = "3.13.15"
const PythonURL = "https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.zip"
const PythonSHA256 = "6479223746cdfb79d25865110d6f524ac98de081324e119af1dc3ae36bddc7a5"

type Instance struct {
	ID              string `json:"id"`
	Name            string `json:"name"`
	Port            int    `json:"port"`
	LAN             bool   `json:"lan"`
	Channel         string `json:"channel"`
	Version         string `json:"version"`
	Commit          string `json:"commit"`
	InstalledAt     string `json:"installed_at,omitempty"`
	UpdatedAt       string `json:"updated_at,omitempty"`
	RecoveredFromID string `json:"recovered_from_id,omitempty"`
	IgnoredUpdate   string `json:"ignored_update,omitempty"`
	VersionTag      string `json:"version_tag,omitempty"`
}
type Task struct {
	creatorResult    json.RawMessage
	ResultInstanceID string   `json:"result_instance_id,omitempty"`
	ID               string   `json:"id"`
	InstanceID       string   `json:"instance_id"`
	Kind             string   `json:"kind"`
	Status           string   `json:"status"`
	Stage            string   `json:"stage"`
	Percent          int      `json:"percent"`
	Error            string   `json:"error,omitempty"`
	Logs             []string `json:"logs"`
	StartedAt        string   `json:"started_at"`
	FinishedAt       string   `json:"finished_at,omitempty"`
	Phase            string   `json:"phase"`
	Cancellable      bool     `json:"cancellable"`
	CancelRequested  bool     `json:"cancel_requested,omitempty"`
	ErrorCode        string   `json:"error_code,omitempty"`
	Retryable        bool     `json:"retryable"`
	TargetTag        string   `json:"target_tag,omitempty"`
	StartAfter       bool     `json:"start_after,omitempty"`
	ctx              context.Context
	cancel           context.CancelFunc
	committing       bool
}
type View struct {
	Instance
	Status   string        `json:"status"`
	URL      string        `json:"url,omitempty"`
	PID      int           `json:"pid,omitempty"`
	DataPath string        `json:"data_path"`
	LANURLs  []string      `json:"lan_urls"`
	Task     *Task         `json:"task,omitempty"`
	Error    string        `json:"error,omitempty"`
	Update   *UpdateStatus `json:"update,omitempty"`
}
type Release struct {
	Version     string `json:"version"`
	Commit      string `json:"commit"`
	Source      string `json:"source"`
	URL         string `json:"url"`
	Tag         string `json:"tag,omitempty"`
	PublishedAt string `json:"published_at,omitempty"`
}
type UpdateStatus struct {
	Latest     *Release `json:"latest,omitempty"`
	Available  bool     `json:"available"`
	Suppressed bool     `json:"suppressed"`
	CheckedAt  string   `json:"checked_at"`
	Error      string   `json:"error,omitempty"`
}
type Config struct {
	Root             string
	Python           string
	LocalSource      string
	BundledSource    string
	BundledCommit    string
	SkipDependencies bool
	SystemPackages   bool
	Preview          bool
}
type state struct {
	Schema      int           `json:"schema"`
	Instances   []Instance    `json:"instances"`
	Quarantined []indexRecord `json:"quarantined,omitempty"`
	IndexBackup string        `json:"index_backup,omitempty"`
}

func ident() string     { b := make([]byte, 16); _, _ = rand.Read(b); return hex.EncodeToString(b) }
func timestamp() string { return time.Now().UTC().Format(time.RFC3339) }
func atomicJSON(path string, value any) error {
	b, e := json.MarshalIndent(value, "", "  ")
	if e != nil {
		return e
	}
	if e = os.MkdirAll(filepath.Dir(path), 0700); e != nil {
		return e
	}
	t := path + ".tmp"
	if e = os.WriteFile(t, b, 0600); e != nil {
		return e
	}
	return os.Rename(t, path)
}
func clone[T any](v T) T {
	b, _ := json.Marshal(v)
	var result T
	_ = json.Unmarshal(b, &result)
	return result
}
func checkName(name string) error {
	if len([]rune(name)) < 1 || len([]rune(name)) > 48 {
		return errors.New("实例名称需要 1–48 个字符")
	}
	for _, r := range name {
		if r < 32 {
			return errors.New("名称不能包含控制字符")
		}
	}
	return nil
}

type runtimeProcess struct {
	PID     int
	done    chan struct{}
	bound   chan struct{}
	stop    func() error
	started time.Time
}
type Manager struct {
	mu              sync.Mutex
	taskWG          sync.WaitGroup
	closed          chan struct{}
	runtimeMu       sync.Mutex
	settingsMu      sync.RWMutex
	runtimeSettings map[string]map[string]string
	remoteMu        sync.Mutex
	remoteCache     map[string]releaseCache
	config          Config
	instances       map[string]*Instance
	tasks           map[string]*Task
	active          map[string]string
	processes       map[string]*runtimeProcess
	errors          map[string]string
	closing         bool
	lock            *os.File
	ctx             context.Context
	cancel          context.CancelFunc
	quarantined     []indexRecord
	indexOriginal   []byte
	indexBackup     string
	updates         map[string]*UpdateStatus
	historyError    string
}

func New(config Config) (*Manager, error) {
	if config.Root == "" {
		return nil, errors.New("需要启动器数据目录")
	}
	config.Root, _ = filepath.Abs(config.Root)
	if err := os.MkdirAll(config.Root, 0700); err != nil {
		return nil, err
	}
	m := &Manager{config: config, closed: make(chan struct{}), instances: map[string]*Instance{}, tasks: map[string]*Task{}, active: map[string]string{}, processes: map[string]*runtimeProcess{}, errors: map[string]string{}, updates: map[string]*UpdateStatus{}}
	var lockErr error
	m.lock, lockErr = acquireLock(filepath.Join(config.Root, "launcher.lock"))
	if lockErr != nil {
		return nil, lockErr
	}
	ready := false
	defer func() {
		if !ready && m.lock != nil {
			m.lock.Close()
		}
	}()
	m.ctx, m.cancel = context.WithCancel(context.Background())
	if e := m.loadIndex(); e != nil {
		m.cancel()
		return nil, e
	}
	for id := range m.instances {
		if e := m.recover(id); e != nil {
			return nil, e
		}
	}
	// Interrupted updates are rolled back before any process can start.
	m.loadTaskHistory()
	ready = true
	return m, nil
}
func (m *Manager) Root() string          { return m.config.Root }
func (m *Manager) path(id string) string { return filepath.Join(m.config.Root, "instances", id) }
func (m *Manager) saveLocked() error {
	rows := []Instance{}
	for _, i := range m.instances {
		rows = append(rows, *i)
	}
	sort.Slice(rows, func(i, j int) bool { return rows[i].ID < rows[j].ID })
	encoded, e := json.MarshalIndent(state{Schema: 1, Instances: rows, Quarantined: m.quarantined, IndexBackup: m.indexBackup}, "", "  ")
	if e != nil {
		return e
	}
	if len(encoded) > (4<<20)-256 {
		return errors.New("索引将超过 4 MiB，未保存；请保留原始备份人工整理")
	}
	if e := m.backupIndexLocked(); e != nil {
		return e
	}
	return atomicJSON(filepath.Join(m.config.Root, "launcher.json"), state{Schema: 1, Instances: rows, Quarantined: m.quarantined, IndexBackup: m.indexBackup})
}
func (m *Manager) Create(name, channel string, port int, lan bool) (View, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.createLocked(name, channel, port, lan)
}

// Caller holds mu, allowing restore to register its destination and task atomically.
func (m *Manager) createLocked(name, channel string, port int, lan bool) (View, error) {
	if channel == "bundled" && m.config.BundledSource == "" {
		return View{}, errors.New("未提供随桌面打包的本体")
	}
	if e := checkName(name); e != nil {
		return View{}, e
	}
	if channel != "release" && channel != "main" && channel != "bundled" {
		return View{}, errors.New("版本通道只支持 bundled / release / main")
	}
	if m.closing {
		return View{}, errors.New("启动器正在退出")
	}
	if len(m.instances) >= 24 {
		return View{}, errors.New("最多管理 24 个实例")
	}
	if port == 0 {
		port = 8180
		for {
			used := false
			for _, i := range m.instances {
				if i.Port == port {
					used = true
					break
				}
			}
			if !used && availablePort(port) == nil {
				break
			}
			if port >= 65535 {
				return View{}, errors.New("没有可用端口，请检查本机服务")
			}
			port++
		}
	}
	if port < 1024 || port > 65535 {
		return View{}, errors.New("端口需在 1024–65535")
	}
	for _, i := range m.instances {
		if i.Port == port {
			return View{}, errors.New("该端口已分配给另一个实例")
		}
	}
	i := &Instance{ID: ident(), Name: name, Channel: channel, Port: port, LAN: lan}
	m.instances[i.ID] = i
	if e := os.MkdirAll(filepath.Join(m.path(i.ID), "data"), 0700); e != nil {
		delete(m.instances, i.ID)
		return View{}, e
	}
	if e := m.saveLocked(); e != nil {
		delete(m.instances, i.ID)
		return View{}, e
	}
	return m.viewLocked(i.ID), nil
}
func (m *Manager) viewLocked(id string) View {
	i := m.instances[id]
	v := View{Instance: *i, Status: "not_installed", DataPath: filepath.Join(m.path(id), "data"), LANURLs: lanURLs(i.Port, i.LAN), Error: m.errors[id]}
	if u := m.updates[id]; u != nil {
		v.Update = clone(u)
	}
	if i.Commit != "" {
		v.Status = "ready"
	}
	if v.Error != "" {
		v.Status = "error"
	}
	if p := m.processes[id]; p != nil {
		v.Status = "running"
		v.PID = p.PID
		v.URL = localURL(i.Port)
	}
	if key := m.active[id]; key != "" {
		if m.tasks[key].Kind != "creator" || m.processes[id] == nil {
			v.Status = "busy"
		}
		v.Task = clone(m.tasks[key])
	}
	return v
}
func (m *Manager) List() []View {
	m.mu.Lock()
	defer m.mu.Unlock()
	result := []View{}
	for id := range m.instances {
		result = append(result, m.viewLocked(id))
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].Name == result[j].Name {
			return result[i].ID < result[j].ID
		}
		return result[i].Name < result[j].Name
	})
	return result
}
func (m *Manager) Get(id string) (View, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.instances[id] == nil {
		return View{}, errors.New("实例不存在")
	}
	return m.viewLocked(id), nil
}
func (m *Manager) Tasks() []Task {
	m.mu.Lock()
	defer m.mu.Unlock()
	rows := []Task{}
	for _, t := range m.tasks {
		row := clone(*t)
		row.Retryable = retryable(row)
		rows = append(rows, row)
	}
	sort.Slice(rows, func(i, j int) bool {
		a, _ := time.Parse(time.RFC3339Nano, rows[i].StartedAt)
		b, _ := time.Parse(time.RFC3339Nano, rows[j].StartedAt)
		if a.Equal(b) {
			return rows[i].ID < rows[j].ID
		}
		return a.Before(b)
	})
	return rows
}
func (m *Manager) task(id, kind string, fn func(*Task) error) (Task, error) {
	return m.taskWithOptions(id, kind, taskOptions{}, fn)
}

type taskOptions struct {
	TargetTag  string
	StartAfter bool
}

func (m *Manager) taskWithOptions(id, kind string, options taskOptions, fn func(*Task) error) (Task, error) {
	m.mu.Lock()
	if m.instances[id] == nil {
		m.mu.Unlock()
		return Task{}, errors.New("实例不存在")
	}
	if m.active[id] != "" {
		m.mu.Unlock()
		return Task{}, errors.New("实例已有任务，请等待完成")
	}
	if m.closing {
		m.mu.Unlock()
		return Task{}, errors.New("启动器正在退出")
	}
	ctx, cancel := context.WithCancel(m.ctx)
	t := &Task{ID: ident(), InstanceID: id, Kind: kind, Status: "running", Stage: "准备任务", Phase: "preparing", Cancellable: kind == "install" || kind == "update" || kind == "switch", Logs: []string{}, StartedAt: timestamp(), ctx: ctx, cancel: cancel}
	t.StartedAt = time.Now().UTC().Format(time.RFC3339Nano)
	t.TargetTag = options.TargetTag
	t.StartAfter = options.StartAfter
	m.tasks[t.ID] = t
	m.active[id] = t.ID
	if kind != "creator" {
		delete(m.errors, id)
	}
	m.persistTaskHistoryLocked()
	snapshot := clone(*t)
	m.taskWG.Add(1)
	m.mu.Unlock()
	go func() {
		defer m.taskWG.Done()
		err := fn(t)
		m.mu.Lock()
		defer m.mu.Unlock()
		if !t.committing && t.CancelRequested {
			err = context.Canceled
		}
		t.cancel()
		t.Cancellable = false
		t.FinishedAt = timestamp()
		delete(m.active, id)
		if errors.Is(err, context.Canceled) && t.CancelRequested {
			t.Status = "cancelled"
			t.Phase = "cancelled"
			t.ErrorCode = "cancelled"
			t.Stage = "已取消准备；原服务与数据保留，可重新开始"
		} else if err != nil {
			t.Status = "failed"
			t.Phase = "failed"
			t.ErrorCode = "operation_failed"
			if errors.Is(err, context.DeadlineExceeded) {
				t.ErrorCode = "timeout"
			}
			t.Error = m.redact(id, err.Error())
			if kind != "creator" {
				m.errors[id] = t.Error
			}
			t.Stage = "未完成，可查看日志重试"
		} else {
			t.Status = "success"
			t.Phase = "completed"
			t.Percent = 100
			t.Stage = "已完成"
		}
		_ = atomicJSON(filepath.Join(m.path(id), "last-task.json"), t)
		m.persistTaskHistoryLocked()
	}()
	return snapshot, nil
}
func (m *Manager) progress(t *Task, p int, stage string) {
	m.mu.Lock()
	if t.CancelRequested && !t.committing {
		m.mu.Unlock()
		return
	}
	t.Percent = p
	t.Stage = stage
	if t.Kind == "install" || t.Kind == "update" || t.Kind == "switch" {
		switch {
		case p < 12:
			t.Phase = "resolving"
		case p < 30:
			t.Phase = "runtime"
		case p < 45:
			t.Phase = "source"
		case p < 71:
			t.Phase = "dependencies"
		case p < 75:
			t.Phase = "validating"
		default:
			t.Phase = "committing"
		}
	}
	m.mu.Unlock()
}
func (m *Manager) log(t *Task, line string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	line = m.redact(t.InstanceID, line)
	t.Logs = append(t.Logs, line)
	if len(t.Logs) > 160 {
		t.Logs = t.Logs[len(t.Logs)-160:]
	}
}
func (m *Manager) Install(id string, start bool) (Task, error) {
	return m.taskWithOptions(id, "install", taskOptions{StartAfter: start}, func(t *Task) error {
		if e := m.install(t, false); e != nil {
			return e
		}
		if start {
			return m.start(id, t)
		}
		return nil
	})
}
func (m *Manager) Update(id string) (Task, error) {
	return m.task(id, "update", func(t *Task) error {
		// Development fixtures deliberately keep their local source.
		if m.config.LocalSource != "" {
			return m.install(t, true)
		}
		r, e := m.Check(id)
		if e != nil {
			return e
		}
		m.mu.Lock()
		current := *m.instances[id]
		m.mu.Unlock()
		if r.Source != "main" {
			ge, e := releaseAtLeastCurrent(r, current)
			if e == nil && !ge {
				m.log(t, "当前本体高于公开发行版，保留当前版本")
				return nil
			}
		}
		return m.installRelease(t, true, &r)
	})
}
func (m *Manager) SwitchVersion(id, tag string) (Task, error) {
	if !validReleaseTag(tag) {
		return Task{}, errors.New("请选择有效的已发布版本")
	}
	return m.taskWithOptions(id, "switch", taskOptions{TargetTag: tag}, func(t *Task) error {
		r, e := ResolveTag(tag)
		if e != nil {
			return e
		}
		return m.installRelease(t, true, &r)
	})
}
func (m *Manager) Start(id string) (Task, error) {
	return m.task(id, "start", func(t *Task) error { return m.start(id, t) })
}
func (m *Manager) Stop(id string) (Task, error) {
	return m.task(id, "stop", func(t *Task) error { m.progress(t, 30, "停止服务并释放端口"); return m.stop(id) })
}
func (m *Manager) Configure(id, name, channel string, port int, lan bool) error {
	if e := checkName(name); e != nil {
		return e
	}
	if port < 1024 || port > 65535 {
		return errors.New("端口范围错误")
	}
	if channel != "release" && channel != "main" && channel != "bundled" {
		return errors.New("通道错误")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	i := m.instances[id]
	if i == nil {
		return errors.New("实例不存在")
	}
	if m.active[id] != "" || m.processes[id] != nil {
		return errors.New("请先停止服务再修改运行设置")
	}
	for key, row := range m.instances {
		if key != id && row.Port == port {
			return errors.New("端口已被其他实例占用")
		}
	}
	i.Name = name
	i.Port = port
	i.LAN = lan
	i.Channel = channel
	return m.saveLocked()
}
func (m *Manager) Close() {
	m.mu.Lock()
	if m.closing {
		closed := m.closed
		m.mu.Unlock()
		if closed != nil {
			<-closed
		}
		return
	}
	m.closing = true
	if m.cancel != nil {
		m.cancel()
	}
	ids := []string{}
	for id := range m.processes {
		ids = append(ids, id)
	}
	m.mu.Unlock()
	for _, id := range ids {
		_ = m.stop(id)
	}
	// Keep the root lock until cancelled preparation / rollback / history
	// writes finish, so a newly opened desktop cannot race those operations.
	m.taskWG.Wait()
	m.mu.Lock()
	ids = nil
	for id := range m.processes {
		ids = append(ids, id)
	}
	m.mu.Unlock()
	for _, id := range ids {
		_ = m.stop(id)
	}
	if m.lock != nil {
		_ = m.lock.Close()
	}
	if m.closed != nil {
		close(m.closed)
	}
}
func validID(id string) bool {
	if len(id) != 32 {
		return false
	}
	_, e := hex.DecodeString(id)
	return e == nil
}
