package engine

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func testManager(t *testing.T) *Manager {
	t.Helper()
	m, e := New(Config{Root: t.TempDir()})
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(m.Close)
	return m
}
func TestCreatePersistentIsolation(t *testing.T) {
	m := testManager(t)
	a, e := m.Create("雾港", "release", 0, false)
	if e != nil {
		t.Fatal(e)
	}
	b, e := m.Create("边境", "main", 0, true)
	if e != nil {
		t.Fatal(e)
	}
	if a.Port == b.Port || a.DataPath == b.DataPath {
		t.Fatal("not isolated")
	}
	m.Close()
	n, e := New(Config{Root: m.Root()})
	if e == nil {
		defer n.Close()
	}
	if e != nil || len(n.List()) != 2 {
		t.Fatal("index not persisted", e)
	}
}
func TestInvalidNameAndPort(t *testing.T) {
	m := testManager(t)
	if _, e := m.Create("", "main", 0, false); e == nil {
		t.Fatal("empty name")
	}
	if _, e := m.Create("ok", "invalid", 0, false); e == nil {
		t.Fatal("channel")
	}
	if _, e := m.Create("ok", "main", 80, false); e == nil {
		t.Fatal("port")
	}
	m.Create("ok", "main", 8180, false)
	if _, e := m.Create("duplicate", "main", 8180, false); e == nil {
		t.Fatal("duplicate port")
	}
}
func TestCredentialsNotReturned(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("test", "main", 0, false)
	if e := m.SaveSettings(i.ID, map[string]string{"TTS_API_KEY": "private-test-key", "TTS_MODEL": "model"}); e != nil {
		t.Fatal(e)
	}
	r, _ := m.Settings(i.ID)
	if r["TTS_API_KEY"] != nil || r["TTS_API_KEY_configured"] != true {
		t.Fatal("secret leaked")
	}
	if !strings.Contains(m.redact(i.ID, "key=private-test-key"), "[已隐藏]") {
		t.Fatal("not redacted")
	}
	if e := m.SaveSettings(i.ID, map[string]string{"DATA_DIR": "/other"}); e == nil {
		t.Fatal("override storage")
	}
}
func makeZIP(t *testing.T, entries map[string]string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "source.zip")
	f, _ := os.Create(p)
	z := zip.NewWriter(f)
	for n, s := range entries {
		w, _ := z.Create(n)
		w.Write([]byte(s))
	}
	z.Close()
	f.Close()
	return p
}
func TestZIPTraversalRejected(t *testing.T) {
	for _, name := range []string{"../outside", "/abs", "root/../../out", "C:/tmp/secret", "root\\escape"} {
		p := makeZIP(t, map[string]string{name: "bad"})
		if e := Extract(p, t.TempDir()); e == nil {
			t.Fatal("unsafe", name)
		}
	}
}
func TestZIPExtractValid(t *testing.T) {
	p := makeZIP(t, map[string]string{"app/server/app.py": "ok", "app/static/index.html": "yes"})
	dst := t.TempDir()
	if e := Extract(p, dst); e != nil {
		t.Fatal(e)
	}
	b, _ := os.ReadFile(filepath.Join(dst, "app/server/app.py"))
	if string(b) != "ok" {
		t.Fatal("extract")
	}
}
func TestHashMismatchNotPromoted(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("test")) }))
	defer server.Close()
	old := HTTPClient
	HTTPClient = server.Client()
	defer func() { HTTPClient = old }()
	dst := filepath.Join(t.TempDir(), "download.exe")
	if e := Download(server.URL, dst, strings.Repeat("0", 64), 1024, nil); e == nil {
		t.Fatal("hash accepted")
	}
	if _, e := os.Stat(dst); !os.IsNotExist(e) {
		t.Fatal("promoted failed asset")
	}
	h := sha256.Sum256([]byte("test"))
	if e := Download(server.URL, dst, hex.EncodeToString(h[:]), 1024, nil); e != nil {
		t.Fatal(e)
	}
}
func TestTaskExclusionAndFailureDataPreserved(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("test", "main", 0, false)
	data := filepath.Join(i.DataPath, "keep")
	os.WriteFile(data, []byte("do not delete"), 0600)
	hold := make(chan struct{})
	task, e := m.task(i.ID, "update", func(t *Task) error { <-hold; return os.ErrInvalid })
	if e != nil {
		t.Fatal(e)
	}
	if _, e = m.task(i.ID, "start", func(t *Task) error { return nil }); e == nil {
		t.Fatal("concurrent task accepted")
	}
	close(hold)
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		m.mu.Lock()
		done := m.tasks[task.ID].Status == "failed"
		m.mu.Unlock()
		if done {
			break
		}
		time.Sleep(time.Millisecond)
	}
	b, _ := os.ReadFile(data)
	if !bytes.Equal(b, []byte("do not delete")) {
		t.Fatal("deleted data")
	}
	v, _ := m.Get(i.ID)
	if v.Status != "error" {
		t.Fatal(v.Status)
	}
}
func TestCorruptIndexFailsClosed(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "launcher.json"), []byte("bad"), 0600)
	if _, e := New(Config{Root: dir}); e == nil {
		t.Fatal("corrupt index ignored")
	}
}
func TestPortBusyDetection(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	defer server.Close()
	var port int
	_, e := fmt.Sscanf(server.URL, "http://127.0.0.1:%d", &port)
	if e != nil {
		t.Fatal(e)
	}
	if e = availablePort(port); e == nil {
		t.Fatal("busy port accepted")
	}
}
func TestInterruptedUpdateRestoresPreviousDataAndApp(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("recover", "main", 0, false)
	root := m.path(i.ID)
	os.MkdirAll(filepath.Join(root, "app"), 0700)
	os.MkdirAll(filepath.Join(root, "previous-app"), 0700)
	os.WriteFile(filepath.Join(root, "app/version"), []byte("bad-new"), 0600)
	os.WriteFile(filepath.Join(root, "previous-app/version"), []byte("good-old"), 0600)
	os.MkdirAll(filepath.Join(root, "previous-data"), 0700)
	os.WriteFile(filepath.Join(root, "previous-data/room"), []byte("original-room"), 0600)
	os.WriteFile(filepath.Join(root, "data/room"), []byte("failed-migration"), 0600)
	atomicJSON(filepath.Join(root, "update-journal.json"), updateJournal{Prior: i.Instance, Python: "old-python", HadApp: true, DataSwap: true})
	m.Close()
	n, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal(e)
	}
	defer n.Close()
	b, _ := os.ReadFile(filepath.Join(root, "app/version"))
	if string(b) != "good-old" {
		t.Fatal("code not recovered")
	}
	b, _ = os.ReadFile(filepath.Join(root, "data/room"))
	if string(b) != "original-room" {
		t.Fatal("data not recovered")
	}
	if _, e = os.Stat(filepath.Join(root, "update-journal.json")); !os.IsNotExist(e) {
		t.Fatal("journal not cleared")
	}
}
func TestConfigDefaultURLsAndNoCredentialInURL(t *testing.T) {
	m := testManager(t)
	i, _ := m.Create("config", "main", 0, false)
	if e := m.SaveSettings(i.ID, map[string]string{"DECISION_BASE_URL": ""}); e != nil {
		t.Fatal(e)
	}
	if e := m.SaveSettings(i.ID, map[string]string{"DECISION_BASE_URL": "https://user:password@example.com/v1"}); e == nil {
		t.Fatal("URL credentials allowed")
	}
	if e := m.SaveSettings(i.ID, map[string]string{"TTS_BASE_URL": "http://external.example/v1"}); e == nil {
		t.Fatal("insecure remote URL")
	}
	if e := m.SaveSettings(i.ID, map[string]string{"TTS_BASE_URL": "http://127.0.0.1:8001/v1"}); e != nil {
		t.Fatal(e)
	}
}
func TestSingleManagerPerDataDirectory(t *testing.T) {
	m := testManager(t)
	if _, e := New(Config{Root: m.Root()}); e == nil {
		t.Fatal("second manager accepted")
	}
	m.Close()
	next, e := New(Config{Root: m.Root()})
	if e != nil {
		t.Fatal("lock not released", e)
	}
	next.Close()
}
func TestDeploymentProtocolRequiresSupportedRuntime(t *testing.T) {
	dir := t.TempDir()
	atomicJSON(filepath.Join(dir, "launcher-manifest.json"), map[string]string{"format": "ember-deploy/v1", "python_series": "3.14", "minimum_launcher": "0.1.0-beta.2", "requirements_file": "requirements-lock.txt", "entrypoint": "server.app:app", "health_path": "/api/health"})
	if e := validateDeployment(dir); e == nil {
		t.Fatal("unsupported Python silently installed")
	}
	atomicJSON(filepath.Join(dir, "launcher-manifest.json"), map[string]string{"format": "ember-deploy/v1", "python_series": "3.13", "minimum_launcher": "9.0.0", "requirements_file": "requirements-lock.txt", "entrypoint": "server.app:app", "health_path": "/api/health"})
	if e := validateDeployment(dir); e == nil {
		t.Fatal("minimum launcher ignored")
	}
}
